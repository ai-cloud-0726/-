#!/usr/bin/env python3
"""
MiniClaw - 自成长自动化助手（单文件整合版）

功能概览：
- 配置中心(config.json)、API 密钥(apikey.json)、能力清单(skll.json)、定时任务(clock.json)
- 多模型路由（文本/视觉/图像生成等）
- 安全命令执行（危险命令黑名单）
- 自纠错机制（失败复盘+策略更新）
- 目标保持（上下文与目标摘要）
- 目标检查（LLM 检查器）
- 看门狗（超时、僵死检测）
- 微信文件传输助手监听（wxauto 可选 + 文件回退模式）
- GUI 操作面板 + Debug 日志
"""

from __future__ import annotations

import json
import logging
import queue
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
    "system_prompt": "你是一个稳健的自动化执行助手，优先使用已有能力，必要时再使用工具，最后才新增能力。",
    "dangerous_commands": [
        "rm -rf /",
        "mkfs",
        "dd if=",
        "shutdown",
        "reboot",
        "poweroff",
        ":(){:|:&};:",
        "chmod -R 777 /",
        "del /f /s /q c:\\",
        "format c:",
    ],
    "allow_shell": True,
    "max_command_seconds": 120,
    "watchdog_interval": 3,
    "self_reflection_enabled": True,
    "goal_check_model": "text-default",
    "memory_keep_last": 40,
    "skill_cleanup_days": 30,
    "wechat": {
        "enabled": True,
        "command_prefix": "小龙虾",
        "stop_words": ["stop", "停止", "停下"],
        "poll_seconds": 2,
    },
    "models": {
        "text-default": {"provider": "openai", "model": "gpt-4o-mini", "role": "text"},
        "vision-default": {"provider": "openai", "model": "gpt-4.1-mini", "role": "vision"},
        "image-default": {"provider": "openai", "model": "gpt-image-1", "role": "image_gen"},
    },
}

DEFAULT_APIKEY = {
    "openai": "",
    "anthropic": "",
    "qwen": "",
    "custom": {},
}

DEFAULT_SKILLS = {
    "skills": [
        {
            "name": "run_shell",
            "description": "执行受控 shell 命令",
            "usage": "run_shell <command>",
            "method": "CommandExecutor.run",
            "source": "built-in",
            "efficiency": 1.0,
            "last_used": None,
            "created_at": None,
        },
        {
            "name": "help",
            "description": "查看系统参数与能力清单",
            "usage": "help",
            "method": "MiniClawEngine.show_help",
            "source": "built-in",
            "efficiency": 1.0,
            "last_used": None,
            "created_at": None,
        },
    ],
    "cleanup_history": [],
}

DEFAULT_CLOCK = {"tasks": []}
DEFAULT_STATE = {
    "current_goal": "",
    "context_memory": [],
    "error_lessons": [],
    "running_task": None,
}


@dataclass
class ClockTask:
    task_id: str
    name: str
    command: str
    interval_seconds: int
    enabled: bool = True
    next_run: float = 0.0


def normalize_text(value: str) -> str:
    return (value or "").strip().lower()


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
    """多模型路由：这里提供统一调用接口，可按 provider 扩展。"""

    def __init__(self, config_store: JsonStore, key_store: JsonStore, logger: logging.Logger):
        self.config_store = config_store
        self.key_store = key_store
        self.logger = logger

    def call_text(self, prompt: str, model_alias: str = "text-default") -> str:
        cfg = self.config_store.load()
        models = cfg.get("models", {})
        model = models.get(model_alias, {})
        provider = model.get("provider", "mock")
        # 可在这里接入真实 SDK；默认使用 mock 返回，避免无 key 时崩溃
        self.logger.debug("Model call: alias=%s provider=%s", model_alias, provider)
        if provider == "mock" or not self.key_store.load().get(provider):
            return f"[MOCK:{model_alias}] 已分析: {prompt[:120]}"
        # 真实调用入口（示例占位）
        return f"[{provider}:{model_alias}] {prompt[:120]}"

    def call_by_role(self, role: str, prompt: str) -> str:
        cfg = self.config_store.load()
        model_alias = None
        for alias, meta in cfg.get("models", {}).items():
            if meta.get("role") == role:
                model_alias = alias
                break
        return self.call_text(prompt, model_alias or "text-default")

    def check_goal(self, goal: str, context: List[str]) -> Dict[str, Any]:
        joined = "\n".join(context[-8:])
        prompt = f"目标: {goal}\n上下文: {joined}\n请判断是否达到目标，输出 PASS/FAIL 与改进建议。"
        result = self.call_text(prompt, self.config_store.load().get("goal_check_model", "text-default"))
        passed = "PASS" in result.upper() and "FAIL" not in result.upper()
        return {"passed": passed, "raw": result, "time": datetime.now().isoformat()}


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
        first_token = normalized.split(" ", 1)[0] if normalized else ""
        for bad in cfg.get("dangerous_commands", []):
            b = normalize_text(bad)
            if not b:
                continue
            if b in normalized or first_token == b:
                return {"ok": False, "error": f"危险命令已拦截: {bad}"}

        timeout = int(cfg.get("max_command_seconds", 120))
        self.logger.info("Executing command: %s", cmd)

        start = time.time()
        try:
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            while process.poll() is None:
                if self.stop_event.is_set():
                    process.terminate()
                    return {"ok": False, "error": "任务被用户停止", "stopped": True}
                if time.time() - start > timeout:
                    process.kill()
                    return {"ok": False, "error": f"命令超时({timeout}s)", "timeout": True}
                time.sleep(0.2)

            out, err = process.communicate()
            return {
                "ok": process.returncode == 0,
                "returncode": process.returncode,
                "stdout": out,
                "stderr": err,
                "elapsed": round(time.time() - start, 2),
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}
        finally:
            self.stop_event.clear()


class SkillManager:
    def __init__(self, skill_store: JsonStore, logger: logging.Logger):
        self.store = skill_store
        self.logger = logger

    def list_skills(self) -> List[Dict[str, Any]]:
        return self.store.load().get("skills", [])

    def add_or_update_skill(self, skill: Dict[str, Any]):
        data = self.store.load()
        skills = data.get("skills", [])
        now = datetime.now().isoformat()
        skill.setdefault("created_at", now)
        skill["last_used"] = now
        for idx, s in enumerate(skills):
            if s.get("name") == skill.get("name"):
                skills[idx].update(skill)
                self.store.save(data)
                return
        skills.append(skill)
        data["skills"] = skills
        self.store.save(data)

    def mark_used(self, name: str, success: bool):
        data = self.store.load()
        for s in data.get("skills", []):
            if s.get("name") == name:
                s["last_used"] = datetime.now().isoformat()
                base = s.get("efficiency", 1.0)
                s["efficiency"] = round(base + 0.02 if success else max(0.1, base - 0.05), 2)
        self.store.save(data)

    def cleanup(self, older_than_days: int = 30):
        data = self.store.load()
        now = time.time()
        kept, removed = [], []
        for s in data.get("skills", []):
            lu = s.get("last_used")
            eff = s.get("efficiency", 1.0)
            if not lu:
                kept.append(s)
                continue
            try:
                age_days = (now - datetime.fromisoformat(lu).timestamp()) / 86400
            except Exception:
                age_days = 0
            if age_days > older_than_days and eff < 0.5 and s.get("source") != "built-in":
                removed.append(s)
            else:
                kept.append(s)
        data["skills"] = kept
        data.setdefault("cleanup_history", []).append(
            {"time": datetime.now().isoformat(), "removed": [x.get("name") for x in removed]}
        )
        self.store.save(data)
        return removed


class ClockScheduler:
    def __init__(self, clock_store: JsonStore, engine_ref: "MiniClawEngine", logger: logging.Logger):
        self.store = clock_store
        self.engine_ref = engine_ref
        self.logger = logger
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()

    def list_tasks(self) -> List[Dict[str, Any]]:
        return self.store.load().get("tasks", [])

    def add_task(self, name: str, command: str, interval_seconds: int) -> str:
        data = self.store.load()
        task = ClockTask(str(uuid.uuid4()), name, command, max(5, interval_seconds), True, time.time() + interval_seconds)
        data.setdefault("tasks", []).append(asdict(task))
        self.store.save(data)
        return task.task_id

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
            data = self.store.load()
            now = time.time()
            dirty = False
            for task in data.get("tasks", []):
                if not task.get("enabled", True):
                    continue
                if now >= float(task.get("next_run", 0)):
                    self.logger.info("Clock task run: %s", task.get("name"))
                    self.engine_ref.submit_command(task.get("command", ""), source=f"clock:{task.get('name')}" )
                    task["next_run"] = now + int(task.get("interval_seconds", 60))
                    dirty = True
            if dirty:
                self.store.save(data)
            time.sleep(1)


class WeChatBridge:
    """优先尝试 wxauto；不可用时使用文件通道模拟文件传输助手。"""

    def __init__(self, config_store: JsonStore, logger: logging.Logger, on_command):
        self.config_store = config_store
        self.logger = logger
        self.on_command = on_command
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

    def send_feedback(self, text: str):
        try:
            if self.wx:
                self.wx.SendMsg(text)
                return
        except Exception as e:
            self.logger.warning("WeChat send failed, fallback file: %s", e)
        with WECHAT_FALLBACK_OUTBOX.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {text}\n")

    def _try_init_wx(self):
        try:
            from wxauto import WeChat  # type: ignore
            self.wx = WeChat()
            self.wx.ChatWith("文件传输助手")
            self.logger.info("wxauto connected to 文件传输助手")
        except Exception as e:
            self.logger.warning("wxauto unavailable, use file fallback: %s", e)
            self.wx = None

    def _loop(self):
        cfg = self.config_store.load().get("wechat", {})
        if not cfg.get("enabled", True):
            return
        self._try_init_wx()
        poll = max(1, int(cfg.get("poll_seconds", 2)))
        prefix = cfg.get("command_prefix", "小龙虾")
        stops = set(cfg.get("stop_words", ["stop", "停止"]))
        WECHAT_FALLBACK_INBOX.touch(exist_ok=True)
        while not self.stop_event.is_set():
            lines = WECHAT_FALLBACK_INBOX.read_text(encoding="utf-8", errors="ignore").splitlines()
            if len(lines) > self.last_size:
                new_lines = lines[self.last_size :]
                self.last_size = len(lines)
                for raw in new_lines:
                    text = raw.strip()
                    if not text:
                        continue
                    if text in stops:
                        self.on_command("stop", "wechat")
                    elif text.startswith(prefix):
                        self.on_command(text[len(prefix):].strip(), "wechat")
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
        self.skills = SkillManager(self.skill_store, self.logger)
        self.scheduler = ClockScheduler(self.clock_store, self, self.logger)
        self.wechat = WeChatBridge(self.config_store, self.logger, self.on_external_command)

        self.cmd_queue: "queue.Queue[Dict[str, str]]" = queue.Queue()
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

        self.scheduler.start()
        self.wechat.start()

    def _init_logger(self):
        self.logger = logging.getLogger("miniclaw")
        self.logger.setLevel(logging.DEBUG)
        for handler in list(self.logger.handlers):
            handler.close()
            self.logger.removeHandler(handler)
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        fh.setFormatter(fmt)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        self.logger.addHandler(fh)
        self.logger.addHandler(sh)

    def submit_command(self, command: str, source: str = "ui"):
        self.cmd_queue.put({"command": command, "source": source})

    def on_external_command(self, command: str, source: str):
        self.logger.info("External command from %s: %s", source, command)
        if command.strip().lower() in {"stop", "停止", "停下"}:
            self.executor.request_stop()
            self.wechat.send_feedback("已收到停止指令，正在终止当前任务。")
            return
        self.submit_command(command, source)

    def _append_context(self, text: str):
        data = self.state_store.load()
        mem = data.get("context_memory", [])
        mem.append(f"[{datetime.now().isoformat()}] {text}")
        keep = int(self.config_store.load().get("memory_keep_last", 40))
        data["context_memory"] = mem[-keep:]
        self.state_store.save(data)

    def _remember_lesson(self, lesson: str):
        data = self.state_store.load()
        lessons = data.get("error_lessons", [])
        lessons.append({"time": datetime.now().isoformat(), "lesson": lesson})
        data["error_lessons"] = lessons[-100:]
        self.state_store.save(data)

    def _select_execution_strategy(self, command: str) -> str:
        # 11. 优先已有能力 -> 工具 -> 新能力
        if command.startswith(("help", "goal ", "add_skill ", "cleanup_skills", "clock ", "skills", "models")):
            return "builtin:internal"
        for s in self.skills.list_skills():
            if s.get("name") in {"help", "run_shell"}:
                continue
            kw = s.get("trigger", "")
            if kw and kw in command:
                return f"skill:{s.get('name')}"
        return "builtin:run_shell"

    def _handle_internal_command(self, command: str) -> Optional[str]:
        if command == "help":
            return self.show_help()
        if command.startswith("goal "):
            goal = command[5:].strip()
            st = self.state_store.load()
            st["current_goal"] = goal
            self.state_store.save(st)
            return f"已更新目标: {goal}"
        if command.startswith("add_skill "):
            payload = command[len("add_skill "):]
            parts = payload.split("|")
            if len(parts) < 5:
                return "格式错误，示例: add_skill name|desc|usage|method|trigger"
            self.skills.add_or_update_skill(
                {
                    "name": parts[0].strip(),
                    "description": parts[1].strip(),
                    "usage": parts[2].strip(),
                    "method": parts[3].strip(),
                    "trigger": parts[4].strip(),
                    "source": "self-developed",
                    "efficiency": 1.0,
                }
            )
            return f"能力已写入 skll.json: {parts[0].strip()}"
        if command == "cleanup_skills":
            days = int(self.config_store.load().get("skill_cleanup_days", 30))
            removed = self.skills.cleanup(days)
            return f"能力清理完成，移除 {len(removed)} 项"
        if command == "skills":
            return json.dumps(self.skills.list_skills(), ensure_ascii=False, indent=2)
        if command == "models":
            return json.dumps(self.config_store.load().get("models", {}), ensure_ascii=False, indent=2)
        if command.startswith("clock "):
            return self._handle_clock_command(command)
        return None

    def _handle_clock_command(self, command: str) -> str:
        parts = command.split()
        if len(parts) < 2:
            return "clock 命令支持: list/add/del/enable/disable"
        action = parts[1]
        if action == "list":
            return json.dumps(self.scheduler.list_tasks(), ensure_ascii=False, indent=2)
        if action == "add":
            # clock add 名称|间隔秒|命令
            payload = command.split("clock add", 1)[-1].strip()
            sec = payload.split("|")
            if len(sec) < 3:
                return "格式错误，示例: clock add 巡检|60|echo hello"
            task_id = self.scheduler.add_task(sec[0].strip(), sec[2].strip(), int(sec[1].strip()))
            return f"定时任务已创建: {task_id}"
        if action == "del" and len(parts) >= 3:
            self.scheduler.delete_task(parts[2])
            return f"定时任务已删除: {parts[2]}"
        if action in {"enable", "disable"} and len(parts) >= 3:
            self.scheduler.update_task(parts[2], enabled=(action == "enable"))
            return f"定时任务已{ '启用' if action == 'enable' else '禁用' }: {parts[2]}"
        return "未识别 clock 子命令"

    def _self_reflect(self, command: str, result: Dict[str, Any]):
        if result.get("ok"):
            return
        reason = result.get("error") or result.get("stderr", "unknown error")
        prompt = (
            f"命令执行失败。命令:{command}\n原因:{reason}\n"
            "请给出防止再次犯错的简洁规则，格式：RULE: ..."
        )
        advice = self.models.call_text(prompt)
        self._remember_lesson(advice)
        self.logger.warning("Self reflection advice: %s", advice)

    def _goal_check(self):
        state = self.state_store.load()
        goal = state.get("current_goal", "")
        if not goal:
            return
        res = self.models.check_goal(goal, state.get("context_memory", []))
        self._append_context(f"目标检查: {res}")

    def _worker_loop(self):
        while True:
            job = self.cmd_queue.get()
            command = (job.get("command") or "").strip()
            source = job.get("source", "unknown")
            if not command:
                continue
            self._append_context(f"收到任务[{source}] {command}")
            strategy = self._select_execution_strategy(command)
            self.logger.debug("Execution strategy: %s", strategy)

            if strategy == "builtin:internal":
                msg = self._handle_internal_command(command) or "未识别的内部命令"
                self._append_context(msg)
                self.wechat.send_feedback(msg)
                self.skills.mark_used("help", True)
                continue

            st = self.state_store.load()
            st["running_task"] = {"command": command, "source": source, "started_at": datetime.now().isoformat()}
            self.state_store.save(st)

            # 看门狗：监控执行线程
            result_box: Dict[str, Any] = {}
            done = threading.Event()

            def runner():
                result_box.update(self.executor.run(command))
                done.set()

            t = threading.Thread(target=runner, daemon=True)
            t.start()
            watchdog_interval = int(self.config_store.load().get("watchdog_interval", 3))
            while not done.wait(watchdog_interval):
                self.logger.warning("Watchdog: command still running => %s", command)
                self.wechat.send_feedback(f"任务仍在执行中: {command[:60]}")

            result = result_box
            ok = result.get("ok", False)
            self.skills.mark_used("run_shell", ok)
            self._append_context(f"执行结果: {result}")
            self.wechat.send_feedback(f"任务完成 ok={ok} result={str(result)[:400]}")

            if not ok and self.config_store.load().get("self_reflection_enabled", True):
                self._self_reflect(command, result)

            st = self.state_store.load()
            st["running_task"] = None
            self.state_store.save(st)

            self._goal_check()

    def show_help(self) -> str:
        cfg = self.config_store.load()
        skills = self.skills.list_skills()
        tasks = self.scheduler.list_tasks()
        info = {
            "agent": cfg.get("agent_name"),
            "purpose": cfg.get("purpose"),
            "system_prompt": cfg.get("system_prompt"),
            "dangerous_commands": cfg.get("dangerous_commands", []),
            "models": list(cfg.get("models", {}).keys()),
            "skills": [{"name": s.get("name"), "usage": s.get("usage")} for s in skills],
            "clock_tasks": [{"name": t.get("name"), "interval_seconds": t.get("interval_seconds")} for t in tasks],
            "commands": [
                "help",
                "goal <目标>",
                "skills",
                "models",
                "add_skill name|desc|usage|method|trigger",
                "cleanup_skills",
                "clock list",
                "clock add 名称|间隔秒|命令",
                "clock del <task_id>",
                "clock enable <task_id>",
                "clock disable <task_id>",
                "<其他命令默认进入受控shell执行>",
            ],
        }
        return json.dumps(info, ensure_ascii=False, indent=2)


class MiniClawGUI:
    def __init__(self, engine: MiniClawEngine):
        self.engine = engine
        self.root = tk.Tk()
        self.root.title("MiniClaw 小龙虾控制台")
        self.root.geometry("980x700")
        self._build()

    def _build(self):
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(frame)
        top.pack(fill=tk.X)

        ttk.Label(top, text="输入命令：").pack(side=tk.LEFT)
        self.entry = ttk.Entry(top)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.entry.bind("<Return>", lambda e: self.run_command())
        ttk.Button(top, text="执行", command=self.run_command).pack(side=tk.LEFT)
        ttk.Button(top, text="停止", command=self.stop_command).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Help", command=self.show_help).pack(side=tk.LEFT)

        mid = ttk.Frame(frame)
        mid.pack(fill=tk.BOTH, expand=True, pady=8)

        self.log_text = scrolledtext.ScrolledText(mid, font=("Consolas", 10))
        self.log_text.pack(fill=tk.BOTH, expand=True)

        bottom = ttk.Frame(frame)
        bottom.pack(fill=tk.X)
        ttk.Button(bottom, text="新增定时任务", command=self.add_clock_task).pack(side=tk.LEFT)
        ttk.Button(bottom, text="刷新日志", command=self.refresh_log).pack(side=tk.LEFT, padx=6)

    def run_command(self):
        cmd = self.entry.get().strip()
        if not cmd:
            return
        self.engine.submit_command(cmd, source="gui")
        self.log_text.insert(tk.END, f"> {cmd}\n")
        self.entry.delete(0, tk.END)

    def stop_command(self):
        self.engine.executor.request_stop()
        self.log_text.insert(tk.END, "[系统] 已请求停止当前任务\n")

    def show_help(self):
        data = self.engine.show_help()
        self.log_text.insert(tk.END, data + "\n")

    def add_clock_task(self):
        popup = tk.Toplevel(self.root)
        popup.title("新增定时任务")
        popup.geometry("400x180")
        ttk.Label(popup, text="任务名").pack()
        n = ttk.Entry(popup)
        n.pack(fill=tk.X, padx=10)
        ttk.Label(popup, text="命令").pack()
        c = ttk.Entry(popup)
        c.pack(fill=tk.X, padx=10)
        ttk.Label(popup, text="间隔秒").pack()
        i = ttk.Entry(popup)
        i.insert(0, "60")
        i.pack(fill=tk.X, padx=10)

        def submit():
            try:
                task_id = self.engine.scheduler.add_task(n.get().strip(), c.get().strip(), int(i.get().strip()))
                self.log_text.insert(tk.END, f"[系统] 定时任务已添加: {task_id}\n")
                popup.destroy()
            except Exception as e:
                messagebox.showerror("错误", str(e))

        ttk.Button(popup, text="保存", command=submit).pack(pady=8)

    def refresh_log(self):
        if LOG_FILE.exists():
            self.log_text.insert(tk.END, LOG_FILE.read_text(encoding="utf-8")[-4000:] + "\n")

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
    engine = MiniClawEngine()
    gui = MiniClawGUI(engine)
    gui.run()


if __name__ == "__main__":
    main()
