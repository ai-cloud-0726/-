#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import queue
import re
import subprocess
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
APIKEY_FILE = BASE_DIR / "apikey.json"
SKILL_FILE = BASE_DIR / "skll.json"
CLOCK_FILE = BASE_DIR / "clock.json"
STATE_FILE = BASE_DIR / "state.json"
LOG_FILE = BASE_DIR / "miniclaw.log"
WECHAT_FALLBACK_INBOX = BASE_DIR / "wechat_inbox.txt"
WECHAT_FALLBACK_OUTBOX = BASE_DIR / "wechat_outbox.txt"

DEFAULT_CONFIG = {
    "agent_name": "小龙虾",
    "purpose": "持续、安全、可解释地完成用户目标，并不断提升能力。",
    "system_prompt": "你是一个稳健的自动化执行助手，优先已有能力，再工具，最后新能力。",
    "dangerous_commands": ["rm -rf /", "mkfs", "dd if=", "shutdown", "reboot", "poweroff"],
    "allow_shell": True,
    "max_command_seconds": 120,
    "watchdog_interval": 3,
    "self_reflection_enabled": True,
    "goal_check_model": "text-default",
    "memory_keep_last": 40,
    "skill_cleanup_days": 30,
    "debug_enabled": True,
    "wechat": {"enabled": True, "command_prefix": "小龙虾", "stop_words": ["stop", "停止", "停下"], "poll_seconds": 2},
    "models": {
        "text-default": {"provider": "openai", "model": "gpt-4o-mini", "role": "text"},
        "vision-default": {"provider": "openai", "model": "gpt-4.1-mini", "role": "vision"},
        "image-default": {"provider": "openai", "model": "gpt-image-1", "role": "image_gen"},
    },
}
DEFAULT_APIKEY = {"openai": "", "anthropic": "", "qwen": "", "custom": {}}
DEFAULT_SKILLS = {
    "skills": [
        {"name": "run_shell", "description": "执行受控 shell 命令", "usage": "run_shell <command>", "method": "CommandExecutor.run", "path": "miniclaw/main.py", "source": "built-in", "efficiency": 1.0, "last_used": None, "created_at": None},
        {"name": "help", "description": "查看系统参数与能力清单", "usage": "help", "method": "MiniClawEngine.show_help", "path": "miniclaw/main.py", "source": "built-in", "efficiency": 1.0, "last_used": None, "created_at": None},
    ],
    "cleanup_history": [],
}
DEFAULT_CLOCK = {"tasks": []}
DEFAULT_STATE = {"current_goal": "", "context_memory": [], "error_lessons": [], "failed_plans": [], "running_task": None}


def normalize_text(v: str) -> str:
    return (v or "").strip().lower()


def contains_cjk(v: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", v or ""))


def looks_like_shell_command(v: str) -> bool:
    t = (v or "").strip()
    if not t:
        return False
    prefixes = ("./", "../", "/", "python", "pip", "git", "ls", "dir", "cd", "echo", "cat", "cp", "mv", "rm", "del", "mkdir", "curl", "wget", "powershell", "cmd")
    tokens = ["&&", "||", "|", ">", "<", "*", "=", "--", "-", ".py", ".sh", ".bat", "\\"]
    return t.lower().startswith(prefixes) or any(x in t for x in tokens)


def mask_key(v: str) -> str:
    if not v:
        return ""
    if len(v) <= 8:
        return "*" * len(v)
    return f"{v[:4]}{'*' * (len(v) - 8)}{v[-4:]}"


@dataclass
class ClockTask:
    task_id: str
    name: str
    command: str
    interval_seconds: int
    enabled: bool = True
    next_run: float = 0.0


class JsonStore:
    def __init__(self, path: Path, default_data: Dict[str, Any]):
        self.path = path
        self.default_data = default_data
        self.lock = threading.Lock()
        self.ensure_file()

    def ensure_file(self):
        if not self.path.exists():
            self.path.write_text(json.dumps(self.default_data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> Dict[str, Any]:
        with self.lock:
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                return json.loads(json.dumps(self.default_data))

    def save(self, data: Dict[str, Any]):
        with self.lock:
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class ModelRouter:
    def __init__(self, config_store: JsonStore, key_store: JsonStore, logger: logging.Logger):
        self.config_store = config_store
        self.key_store = key_store
        self.logger = logger

    def call_text(self, prompt: str, model_alias: str = "text-default") -> str:
        models = self.config_store.load().get("models", {})
        provider = models.get(model_alias, {}).get("provider", "mock")
        self.logger.debug("Model call: alias=%s provider=%s", model_alias, provider)
        if provider == "mock" or not self.key_store.load().get(provider):
            return f"[MOCK:{model_alias}] 已分析: {prompt[:120]}"
        return f"[{provider}:{model_alias}] {prompt[:120]}"

    def call_by_role(self, role: str, prompt: str) -> str:
        models = self.config_store.load().get("models", {})
        alias = next((a for a, m in models.items() if m.get("role") == role), "text-default")
        return self.call_text(prompt, alias)

    def check_goal(self, goal: str, context: List[str]) -> Dict[str, Any]:
        prompt = f"目标: {goal}\n上下文: {' '.join(context[-8:])}\n判断 PASS/FAIL 并给出建议"
        r = self.call_text(prompt, self.config_store.load().get("goal_check_model", "text-default"))
        return {"passed": "PASS" in r.upper() and "FAIL" not in r.upper(), "raw": r, "time": datetime.now().isoformat()}


class CommandExecutor:
    def __init__(self, config_store: JsonStore, logger: logging.Logger):
        self.config_store = config_store
        self.logger = logger
        self.stop_event = threading.Event()

    def request_stop(self):
        self.stop_event.set()

    def run(self, cmd: str) -> Dict[str, Any]:
        cfg = self.config_store.load()
        if not cfg.get("allow_shell", False):
            return {"ok": False, "error": "Shell execution disabled by config."}
        normalized = normalize_text(cmd)
        first = normalized.split(" ", 1)[0] if normalized else ""
        for bad in cfg.get("dangerous_commands", []):
            b = normalize_text(bad)
            if b and (b in normalized or b == first):
                return {"ok": False, "error": f"危险命令已拦截: {bad}"}
        start = time.time()
        timeout = int(cfg.get("max_command_seconds", 120))
        self.logger.info("Executing command: %s", cmd)
        try:
            p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            while p.poll() is None:
                if self.stop_event.is_set():
                    p.terminate()
                    return {"ok": False, "error": "任务被用户停止", "stopped": True}
                if time.time() - start > timeout:
                    p.kill()
                    return {"ok": False, "error": f"命令超时({timeout}s)", "timeout": True}
                time.sleep(0.2)
            out, err = p.communicate()
            return {"ok": p.returncode == 0, "returncode": p.returncode, "stdout": out, "stderr": err, "elapsed": round(time.time() - start, 2)}
        except Exception as e:
            return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}
        finally:
            self.stop_event.clear()


class SkillManager:
    def __init__(self, store: JsonStore):
        self.store = store

    def list_skills(self) -> List[Dict[str, Any]]:
        return self.store.load().get("skills", [])

    def add_or_update_skill(self, skill: Dict[str, Any]):
        data = self.store.load()
        skills = data.get("skills", [])
        now = datetime.now().isoformat()
        skill.setdefault("created_at", now)
        skill["last_used"] = now
        for i, s in enumerate(skills):
            if s.get("name") == skill.get("name"):
                skills[i].update(skill)
                self.store.save(data)
                return
        skills.append(skill)
        data["skills"] = skills
        self.store.save(data)

    def delete_skill(self, name: str):
        data = self.store.load()
        data["skills"] = [s for s in data.get("skills", []) if s.get("name") != name]
        self.store.save(data)

    def mark_used(self, name: str, ok: bool):
        data = self.store.load()
        for s in data.get("skills", []):
            if s.get("name") == name:
                s["last_used"] = datetime.now().isoformat()
                base = s.get("efficiency", 1.0)
                s["efficiency"] = round(base + 0.02 if ok else max(0.1, base - 0.05), 2)
        self.store.save(data)

    def cleanup(self, older_than_days: int = 30):
        data = self.store.load()
        now = time.time()
        keep, rm = [], []
        for s in data.get("skills", []):
            lu = s.get("last_used")
            if not lu or s.get("source") == "built-in":
                keep.append(s)
                continue
            age = (now - datetime.fromisoformat(lu).timestamp()) / 86400
            if age > older_than_days and s.get("efficiency", 1.0) < 0.5:
                rm.append(s)
            else:
                keep.append(s)
        data["skills"] = keep
        data.setdefault("cleanup_history", []).append({"time": datetime.now().isoformat(), "removed": [x.get("name") for x in rm]})
        self.store.save(data)
        return rm


class ClockScheduler:
    def __init__(self, store: JsonStore, engine: "MiniClawEngine", logger: logging.Logger):
        self.store, self.engine, self.logger = store, engine, logger
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def list_tasks(self) -> List[Dict[str, Any]]:
        return self.store.load().get("tasks", [])

    def add_task(self, name: str, command: str, interval_seconds: int) -> str:
        data = self.store.load()
        t = ClockTask(str(uuid.uuid4()), name, command, max(5, interval_seconds), True, time.time() + interval_seconds)
        data.setdefault("tasks", []).append(asdict(t))
        self.store.save(data)
        return t.task_id

    def update_task(self, task_id: str, **kwargs):
        data = self.store.load()
        for t in data.get("tasks", []):
            if t.get("task_id") == task_id:
                t.update(kwargs)
        self.store.save(data)

    def delete_task(self, task_id: str):
        data = self.store.load()
        data["tasks"] = [t for t in data.get("tasks", []) if t.get("task_id") != task_id]
        self.store.save(data)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def _loop(self):
        while not self.stop_event.is_set():
            now = time.time()
            data, dirty = self.store.load(), False
            for t in data.get("tasks", []):
                if t.get("enabled", True) and now >= float(t.get("next_run", 0)):
                    self.engine.submit_command(t.get("command", ""), source=f"clock:{t.get('name')}")
                    t["next_run"] = now + int(t.get("interval_seconds", 60))
                    dirty = True
            if dirty:
                self.store.save(data)
            time.sleep(1)


class WeChatBridge:
    def __init__(self, config_store: JsonStore, logger: logging.Logger, on_command):
        self.config_store, self.logger, self.on_command = config_store, logger, on_command
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.last_size = 0
        self.wx = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def _try_init_wx(self):
        try:
            from wxauto import WeChat  # type: ignore
            self.wx = WeChat(); self.wx.ChatWith("文件传输助手")
        except Exception as e:
            self.logger.warning("wxauto unavailable, use file fallback: %s", e)
            self.wx = None

    def send_feedback(self, text: str):
        try:
            if self.wx:
                self.wx.SendMsg(text); return
        except Exception:
            pass
        with WECHAT_FALLBACK_OUTBOX.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {text}\n")

    def _loop(self):
        cfg = self.config_store.load().get("wechat", {})
        if not cfg.get("enabled", True):
            return
        self._try_init_wx()
        poll = max(1, int(cfg.get("poll_seconds", 2)))
        prefix, stops = cfg.get("command_prefix", "小龙虾"), set(cfg.get("stop_words", ["stop", "停止"]))
        WECHAT_FALLBACK_INBOX.touch(exist_ok=True)
        while not self.stop_event.is_set():
            lines = WECHAT_FALLBACK_INBOX.read_text(encoding="utf-8", errors="ignore").splitlines()
            if len(lines) > self.last_size:
                for raw in lines[self.last_size:]:
                    t = raw.strip()
                    if t in stops:
                        self.on_command("stop", "wechat")
                    elif t.startswith(prefix):
                        self.on_command(t[len(prefix):].strip(), "wechat")
                self.last_size = len(lines)
            time.sleep(poll)


class MiniClawEngine:
    def __init__(self):
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        self._init_logger()
        self.config_store = JsonStore(CONFIG_FILE, DEFAULT_CONFIG)
        self.key_store = JsonStore(APIKEY_FILE, DEFAULT_APIKEY)
        self.skill_store = JsonStore(SKILL_FILE, DEFAULT_SKILLS)
        self.clock_store = JsonStore(CLOCK_FILE, DEFAULT_CLOCK)
        self.state_store = JsonStore(STATE_FILE, DEFAULT_STATE)

        self.models = ModelRouter(self.config_store, self.key_store, self.logger)
        self.executor = CommandExecutor(self.config_store, self.logger)
        self.skills = SkillManager(self.skill_store)
        self.scheduler = ClockScheduler(self.clock_store, self, self.logger)
        self.wechat = WeChatBridge(self.config_store, self.logger, self.on_external_command)

        self.cmd_queue: "queue.Queue[Dict[str, str]]" = queue.Queue()
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        self.scheduler.start(); self.wechat.start()

    def _init_logger(self):
        self.logger = logging.getLogger("miniclaw")
        self.logger.setLevel(logging.DEBUG)
        for h in list(self.logger.handlers):
            h.close(); self.logger.removeHandler(h)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8"); fh.setFormatter(fmt)
        sh = logging.StreamHandler(); sh.setFormatter(fmt)
        self.logger.addHandler(fh); self.logger.addHandler(sh)

    def apply_debug_level(self):
        debug = bool(self.config_store.load().get("debug_enabled", True))
        self.logger.setLevel(logging.DEBUG if debug else logging.INFO)

    def submit_command(self, command: str, source: str = "ui"):
        self.cmd_queue.put({"command": command, "source": source})

    def on_external_command(self, command: str, source: str):
        if command.strip().lower() in {"stop", "停止", "停下"}:
            self.executor.request_stop(); self.wechat.send_feedback("已收到停止指令，正在终止当前任务。"); return
        self.submit_command(command, source)

    def _append_context(self, text: str):
        d = self.state_store.load(); mem = d.get("context_memory", [])
        mem.append(f"[{datetime.now().isoformat()}] {text}")
        d["context_memory"] = mem[-int(self.config_store.load().get("memory_keep_last", 40)):]
        self.state_store.save(d)

    def _record_failed_plan(self, command: str, reason: str):
        d = self.state_store.load()
        plans = d.get("failed_plans", [])
        plans.append({"time": datetime.now().isoformat(), "command": command, "reason": reason})
        d["failed_plans"] = plans[-200:]
        self.state_store.save(d)

    def _should_avoid_repeat(self, command: str) -> bool:
        plans = self.state_store.load().get("failed_plans", [])
        recent_same = [p for p in plans[-20:] if normalize_text(p.get("command", "")) == normalize_text(command)]
        return len(recent_same) >= 2

    def _select_execution_strategy(self, command: str) -> str:
        if command.startswith(("help", "goal ", "add_skill ", "cleanup_skills", "clock ", "skills", "models", "chat ")):
            return "builtin:internal"
        if contains_cjk(command) and not looks_like_shell_command(command):
            return "builtin:chat"
        for s in self.skills.list_skills():
            if s.get("name") in {"help", "run_shell"}:
                continue
            kw = s.get("trigger", "")
            if kw and kw in command:
                return f"skill:{s.get('name')}"
        return "builtin:run_shell"

    def _handle_chat_command(self, command: str) -> str:
        prompt = command[5:].strip() if command.startswith("chat ") else command
        if not prompt:
            return "请输入要咨询的内容，例如：chat 帮我总结今天计划"
        return f"[chat] {self.models.call_by_role('text', prompt)}"

    def _handle_internal_command(self, command: str) -> Optional[str]:
        if command == "help":
            return self.show_help()
        if command.startswith("goal "):
            goal = command[5:].strip(); d = self.state_store.load(); d["current_goal"] = goal; self.state_store.save(d); return f"已更新目标: {goal}"
        if command.startswith("add_skill "):
            p = command[len("add_skill "):].split("|")
            if len(p) < 5:
                return "格式错误，示例: add_skill name|desc|usage|method|trigger"
            self.skills.add_or_update_skill({"name": p[0].strip(), "description": p[1].strip(), "usage": p[2].strip(), "method": p[3].strip(), "trigger": p[4].strip(), "path": "miniclaw/main.py", "source": "self-developed", "efficiency": 1.0})
            return f"能力已写入 skll.json: {p[0].strip()}"
        if command == "cleanup_skills":
            rm = self.skills.cleanup(int(self.config_store.load().get("skill_cleanup_days", 30))); return f"能力清理完成，移除 {len(rm)} 项"
        if command == "skills":
            return json.dumps(self.skills.list_skills(), ensure_ascii=False, indent=2)
        if command == "models":
            cfg = self.config_store.load().get("models", {})
            keys = {k: mask_key(v) for k, v in self.key_store.load().items() if isinstance(v, str)}
            return json.dumps({"models": cfg, "apikey_masked": keys}, ensure_ascii=False, indent=2)
        if command.startswith("chat "):
            return self._handle_chat_command(command)
        if command.startswith("clock "):
            return self._handle_clock_command(command)
        return None

    def _handle_clock_command(self, command: str) -> str:
        parts = command.split()
        if len(parts) < 2:
            return "clock 命令支持: list/add/del/enable/disable"
        action = parts[1]
        if action == "list": return json.dumps(self.scheduler.list_tasks(), ensure_ascii=False, indent=2)
        if action == "add":
            sec = command.split("clock add", 1)[-1].strip().split("|")
            if len(sec) < 3: return "格式错误，示例: clock add 巡检|60|echo hello"
            return f"定时任务已创建: {self.scheduler.add_task(sec[0].strip(), sec[2].strip(), int(sec[1].strip()))}"
        if action == "del" and len(parts) >= 3:
            self.scheduler.delete_task(parts[2]); return f"定时任务已删除: {parts[2]}"
        if action in {"enable", "disable"} and len(parts) >= 3:
            self.scheduler.update_task(parts[2], enabled=(action == "enable")); return f"定时任务已{'启用' if action=='enable' else '禁用'}: {parts[2]}"
        return "未识别 clock 子命令"

    def _self_reflect(self, command: str, result: Dict[str, Any]):
        reason = result.get("error") or result.get("stderr", "unknown error")
        advice = self.models.call_text(f"命令执行失败。命令:{command}\n原因:{reason}\n请输出 RULE")
        d = self.state_store.load(); lessons = d.get("error_lessons", []); lessons.append({"time": datetime.now().isoformat(), "lesson": advice}); d["error_lessons"] = lessons[-100:]; self.state_store.save(d)

    def _goal_check(self):
        d = self.state_store.load(); goal = d.get("current_goal", "")
        if goal:
            self._append_context(f"目标检查: {self.models.check_goal(goal, d.get('context_memory', []))}")

    def _worker_loop(self):
        while True:
            job = self.cmd_queue.get(); command = (job.get("command") or "").strip(); source = job.get("source", "unknown")
            if not command: continue
            self._append_context(f"收到任务[{source}] {command}")
            strategy = self._select_execution_strategy(command)
            self.logger.debug("Execution strategy: %s", strategy)
            if strategy == "builtin:internal":
                msg = self._handle_internal_command(command) or "未识别的内部命令"; self._append_context(msg); self.wechat.send_feedback(msg); self.skills.mark_used("help", True); continue
            if strategy == "builtin:chat":
                msg = self._handle_chat_command(command); self._append_context(msg); self.wechat.send_feedback(msg); continue
            if self._should_avoid_repeat(command):
                msg = f"检测到重复失败风险，已跳过: {command}"
                self._append_context(msg); self.wechat.send_feedback(msg); continue

            d = self.state_store.load(); d["running_task"] = {"command": command, "source": source, "started_at": datetime.now().isoformat()}; self.state_store.save(d)
            result_box: Dict[str, Any] = {}; done = threading.Event()

            def runner(): result_box.update(self.executor.run(command)); done.set()

            threading.Thread(target=runner, daemon=True).start()
            while not done.wait(int(self.config_store.load().get("watchdog_interval", 3))):
                self.logger.warning("Watchdog: command still running => %s", command)
                self.wechat.send_feedback(f"任务仍在执行中: {command[:60]}")

            result = result_box; ok = result.get("ok", False); self.skills.mark_used("run_shell", ok)
            self._append_context(f"执行结果: {result}"); self.wechat.send_feedback(f"任务完成 ok={ok} result={str(result)[:400]}")
            if not ok:
                reason = result.get("error") or result.get("stderr", "")
                self._record_failed_plan(command, str(reason)[:280])
                if self.config_store.load().get("self_reflection_enabled", True): self._self_reflect(command, result)
            d = self.state_store.load(); d["running_task"] = None; self.state_store.save(d)
            self._goal_check()

    def show_help(self) -> str:
        cfg = self.config_store.load(); skills = self.skills.list_skills(); tasks = self.scheduler.list_tasks()
        keys = {k: mask_key(v) for k, v in self.key_store.load().items() if isinstance(v, str)}
        info = {
            "agent": cfg.get("agent_name"), "purpose": cfg.get("purpose"), "system_prompt": cfg.get("system_prompt"),
            "debug_enabled": cfg.get("debug_enabled", True), "dangerous_commands": cfg.get("dangerous_commands", []),
            "models": cfg.get("models", {}), "apikey_masked": keys,
            "skills": [{"name": s.get("name"), "usage": s.get("usage"), "path": s.get("path"), "description": s.get("description")} for s in skills],
            "clock_tasks": [{"name": t.get("name"), "interval_seconds": t.get("interval_seconds")} for t in tasks],
            "commands": ["help", "goal <目标>", "skills", "models", "chat <问题>", "add_skill name|desc|usage|method|trigger", "cleanup_skills", "clock list", "clock add 名称|间隔秒|命令", "clock del <task_id>", "clock enable <task_id>", "clock disable <task_id>"],
        }
        return json.dumps(info, ensure_ascii=False, indent=2)


class SkillManagerDialog(tk.Toplevel):
    def __init__(self, parent, engine: MiniClawEngine):
        super().__init__(parent)
        self.engine = engine
        self.title("能力管理")
        self.geometry("980x520")
        self.tree = ttk.Treeview(self, columns=("name", "usage", "path", "description"), show="headings")
        for c, w in [("name", 140), ("usage", 220), ("path", 200), ("description", 380)]:
            self.tree.heading(c, text=c); self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        frm = ttk.Frame(self); frm.pack(fill=tk.X, padx=8, pady=4)
        self.name = ttk.Entry(frm); self.usage = ttk.Entry(frm); self.path = ttk.Entry(frm); self.desc = ttk.Entry(frm); self.method = ttk.Entry(frm); self.trigger = ttk.Entry(frm)
        for i, (lab, ent) in enumerate([("名称", self.name), ("用法", self.usage), ("路径", self.path), ("介绍", self.desc), ("调用方法", self.method), ("触发词", self.trigger)]):
            ttk.Label(frm, text=lab).grid(row=0, column=2*i, sticky="w"); ent.grid(row=0, column=2*i+1, sticky="ew", padx=3)
            frm.grid_columnconfigure(2*i+1, weight=1)

        btn = ttk.Frame(self); btn.pack(fill=tk.X, padx=8, pady=4)
        ttk.Button(btn, text="新增/更新", command=self.upsert).pack(side=tk.LEFT)
        ttk.Button(btn, text="删除", command=self.delete).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn, text="刷新", command=self.refresh).pack(side=tk.LEFT)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.refresh()

    def refresh(self):
        for x in self.tree.get_children(): self.tree.delete(x)
        for s in self.engine.skills.list_skills():
            self.tree.insert("", tk.END, values=(s.get("name"), s.get("usage"), s.get("path", ""), s.get("description", "")))

    def on_select(self, _):
        sel = self.tree.selection()
        if not sel: return
        vals = self.tree.item(sel[0], "values")
        self.name.delete(0, tk.END); self.name.insert(0, vals[0])
        self.usage.delete(0, tk.END); self.usage.insert(0, vals[1])
        self.path.delete(0, tk.END); self.path.insert(0, vals[2])
        self.desc.delete(0, tk.END); self.desc.insert(0, vals[3])

    def upsert(self):
        if not self.name.get().strip():
            return messagebox.showwarning("提示", "名称不能为空")
        self.engine.skills.add_or_update_skill({
            "name": self.name.get().strip(), "usage": self.usage.get().strip(), "path": self.path.get().strip(),
            "description": self.desc.get().strip(), "method": self.method.get().strip() or "custom", "trigger": self.trigger.get().strip(),
            "source": "self-developed", "efficiency": 1.0,
        })
        self.refresh()

    def delete(self):
        n = self.name.get().strip()
        if not n: return
        self.engine.skills.delete_skill(n); self.refresh()


class MiniClawGUI:
    def __init__(self, engine: MiniClawEngine):
        self.engine = engine
        self.root = tk.Tk()
        self.root.title("MiniClaw 小龙虾控制台")
        self.root.geometry("1280x760")
        self._build_menu()
        self._build()
        self.refresh_side_panels()

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        settings = tk.Menu(menubar, tearoff=0)
        settings.add_checkbutton(label="Debug 调试开关", command=self.toggle_debug)
        settings.add_command(label="模型与Key配置", command=self.open_model_settings)
        settings.add_command(label="危险命令配置", command=self.open_danger_settings)
        menubar.add_cascade(label="设置", menu=settings)

        manage = tk.Menu(menubar, tearoff=0)
        manage.add_command(label="能力管理", command=self.open_skill_manager)
        manage.add_command(label="查看帮助", command=self.show_help)
        menubar.add_cascade(label="管理", menu=manage)
        self.root.config(menu=menubar)

    def _build(self):
        main = ttk.Frame(self.root, padding=8); main.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(main); top.pack(fill=tk.X)
        ttk.Label(top, text="输入命令：").pack(side=tk.LEFT)
        self.entry = ttk.Entry(top); self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.entry.bind("<Return>", lambda _: self.run_command())
        ttk.Button(top, text="执行", command=self.run_command).pack(side=tk.LEFT)
        ttk.Button(top, text="停止", command=self.stop_command).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Help", command=self.show_help).pack(side=tk.LEFT)

        paned = ttk.Panedwindow(main, orient=tk.HORIZONTAL); paned.pack(fill=tk.BOTH, expand=True, pady=6)
        left = ttk.Labelframe(paned, text="能力清单")
        center = ttk.Labelframe(paned, text="执行日志")
        right = ttk.Labelframe(paned, text="执行方案失败清单")
        paned.add(left, weight=1); paned.add(center, weight=3); paned.add(right, weight=2)

        self.skill_tree = ttk.Treeview(left, columns=("name", "usage"), show="headings")
        self.skill_tree.heading("name", text="能力"); self.skill_tree.heading("usage", text="用法")
        self.skill_tree.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.log_text = scrolledtext.ScrolledText(center, font=("Consolas", 10))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.fail_tree = ttk.Treeview(right, columns=("time", "command", "reason"), show="headings")
        for c, w in [("time", 130), ("command", 140), ("reason", 220)]:
            self.fail_tree.heading(c, text=c); self.fail_tree.column(c, width=w, anchor="w")
        self.fail_tree.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        bottom = ttk.Frame(main); bottom.pack(fill=tk.X)
        ttk.Button(bottom, text="新增定时任务", command=self.add_clock_task).pack(side=tk.LEFT)
        ttk.Button(bottom, text="刷新日志", command=self.refresh_log).pack(side=tk.LEFT, padx=6)
        ttk.Button(bottom, text="刷新侧栏", command=self.refresh_side_panels).pack(side=tk.LEFT)

    def refresh_side_panels(self):
        for x in self.skill_tree.get_children(): self.skill_tree.delete(x)
        for s in self.engine.skills.list_skills():
            self.skill_tree.insert("", tk.END, values=(s.get("name"), s.get("usage")))
        for x in self.fail_tree.get_children(): self.fail_tree.delete(x)
        for f in self.engine.state_store.load().get("failed_plans", [])[-120:]:
            self.fail_tree.insert("", tk.END, values=(f.get("time", "")[-19:], f.get("command", ""), f.get("reason", "")))

    def open_skill_manager(self):
        SkillManagerDialog(self.root, self.engine)

    def toggle_debug(self):
        cfg = self.engine.config_store.load(); cfg["debug_enabled"] = not cfg.get("debug_enabled", True); self.engine.config_store.save(cfg)
        self.engine.apply_debug_level()
        messagebox.showinfo("设置", f"debug_enabled={cfg['debug_enabled']}")

    def open_model_settings(self):
        win = tk.Toplevel(self.root); win.title("模型与Key配置"); win.geometry("860x460")
        txt = scrolledtext.ScrolledText(win)
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        models = self.engine.config_store.load().get("models", {})
        keys = self.engine.key_store.load()
        txt.insert(tk.END, "# 模型配置(JSON)\n" + json.dumps(models, ensure_ascii=False, indent=2) + "\n\n")
        txt.insert(tk.END, "# API Key(脱敏展示)\n" + json.dumps({k: mask_key(v) if isinstance(v, str) else v for k, v in keys.items()}, ensure_ascii=False, indent=2) + "\n")
        ttk.Label(win, text="如需修改key请直接编辑 apikey.json（界面仅脱敏展示）").pack(anchor="w", padx=8)

    def open_danger_settings(self):
        win = tk.Toplevel(self.root); win.title("危险命令配置"); win.geometry("700x400")
        txt = scrolledtext.ScrolledText(win); txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        cfg = self.engine.config_store.load(); txt.insert(tk.END, "\n".join(cfg.get("dangerous_commands", [])))

        def save():
            cfg2 = self.engine.config_store.load()
            cfg2["dangerous_commands"] = [x.strip() for x in txt.get("1.0", tk.END).splitlines() if x.strip()]
            self.engine.config_store.save(cfg2)
            messagebox.showinfo("保存", "危险命令列表已保存")

        ttk.Button(win, text="保存", command=save).pack(pady=6)

    def run_command(self):
        cmd = self.entry.get().strip()
        if not cmd: return
        self.engine.submit_command(cmd, source="gui")
        self.log_text.insert(tk.END, f"> {cmd}\n")
        self.entry.delete(0, tk.END)
        self.root.after(600, self.refresh_side_panels)

    def stop_command(self):
        self.engine.executor.request_stop(); self.log_text.insert(tk.END, "[系统] 已请求停止当前任务\n")

    def show_help(self):
        self.log_text.insert(tk.END, self.engine.show_help() + "\n")

    def add_clock_task(self):
        pop = tk.Toplevel(self.root); pop.title("新增定时任务"); pop.geometry("430x200")
        ttk.Label(pop, text="任务名").pack(); n = ttk.Entry(pop); n.pack(fill=tk.X, padx=10)
        ttk.Label(pop, text="命令").pack(); c = ttk.Entry(pop); c.pack(fill=tk.X, padx=10)
        ttk.Label(pop, text="间隔秒").pack(); i = ttk.Entry(pop); i.insert(0, "60"); i.pack(fill=tk.X, padx=10)

        def submit():
            try:
                tid = self.engine.scheduler.add_task(n.get().strip(), c.get().strip(), int(i.get().strip()))
                self.log_text.insert(tk.END, f"[系统] 定时任务已添加: {tid}\n")
                pop.destroy()
            except Exception as e:
                messagebox.showerror("错误", str(e))

        ttk.Button(pop, text="保存", command=submit).pack(pady=6)

    def refresh_log(self):
        if LOG_FILE.exists():
            self.log_text.insert(tk.END, LOG_FILE.read_text(encoding="utf-8")[-4000:] + "\n")
        self.refresh_side_panels()

    def run(self):
        self.root.mainloop()


def ensure_seed_files():
    JsonStore(CONFIG_FILE, DEFAULT_CONFIG).ensure_file()
    JsonStore(APIKEY_FILE, DEFAULT_APIKEY).ensure_file()
    JsonStore(SKILL_FILE, DEFAULT_SKILLS).ensure_file()
    JsonStore(CLOCK_FILE, DEFAULT_CLOCK).ensure_file()
    JsonStore(STATE_FILE, DEFAULT_STATE).ensure_file()
    WECHAT_FALLBACK_INBOX.touch(exist_ok=True)
    WECHAT_FALLBACK_OUTBOX.touch(exist_ok=True)


def main():
    ensure_seed_files()
    engine = MiniClawEngine(); engine.apply_debug_level()
    MiniClawGUI(engine).run()


if __name__ == "__main__":
    main()
