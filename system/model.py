from __future__ import annotations

import json
import os
from urllib.error import URLError
from urllib.request import Request, urlopen
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass
class ModelTransport:
    base_url: str
    api_path: str
    headers: Dict[str, str]
    api_key_env: str


@dataclass
class ModelPaths:
    model_cache_dir: str
    prompt_trace_file: str
    response_trace_file: str


@dataclass
class ModelProfile:
    provider: str
    model: str
    temperature: float
    max_tokens: int
    timeout_sec: int
    max_retries: int
    transport: ModelTransport
    paths: ModelPaths


class ModelClient:
    """Unified LLM call wrapper. All model-related configuration is sourced from models.json."""

    def __init__(self, models_config: Dict[str, Any]):
        self.models_config = models_config
        self.active_profile_name = str(models_config.get("active_profile", "default"))
        profiles = models_config.get("profiles", {})
        if not isinstance(profiles, dict) or not profiles:
            raise ValueError("models.json missing 'profiles' configuration")
        if self.active_profile_name not in profiles:
            raise ValueError(f"active_profile '{self.active_profile_name}' not found in models.json profiles")
        self.profile = self._build_profile(profiles[self.active_profile_name])
        self._ensure_model_paths()

    def _build_profile(self, payload: Dict[str, Any]) -> ModelProfile:
        transport_cfg = payload.get("transport", {})
        paths_cfg = payload.get("paths", {})
        transport = ModelTransport(
            base_url=str(transport_cfg.get("base_url", "")),
            api_path=str(transport_cfg.get("api_path", "")),
            headers=dict(transport_cfg.get("headers", {})),
            api_key_env=str(transport_cfg.get("api_key_env", "OPENAI_API_KEY")),
        )
        paths = ModelPaths(
            model_cache_dir=str(paths_cfg.get("model_cache_dir", "runtime/model_cache")),
            prompt_trace_file=str(paths_cfg.get("prompt_trace_file", "runtime/model_prompt_trace.jsonl")),
            response_trace_file=str(paths_cfg.get("response_trace_file", "runtime/model_response_trace.jsonl")),
        )
        return ModelProfile(
            provider=str(payload.get("provider", "mock")),
            model=str(payload.get("model", "unknown")),
            temperature=float(payload.get("temperature", 0.2)),
            max_tokens=int(payload.get("max_tokens", 1024)),
            timeout_sec=int(payload.get("timeout_sec", 30)),
            max_retries=int(payload.get("max_retries", 1)),
            transport=transport,
            paths=paths,
        )

    def _ensure_model_paths(self) -> None:
        Path(self.profile.paths.model_cache_dir).mkdir(parents=True, exist_ok=True)
        for trace_file in [self.profile.paths.prompt_trace_file, self.profile.paths.response_trace_file]:
            path = Path(trace_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text("", encoding="utf-8")

    def _trace(self, path_str: str, payload: Dict[str, Any]) -> None:
        path = Path(path_str)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _estimate_tokens(self, text: str) -> int:
        # lightweight estimate for local dashboarding (about 4 chars ~= 1 token)
        text = text or ""
        return max(1, (len(text) + 3) // 4)

    def generate(self, prompt: str, context: Dict[str, Any]) -> str:
        goal = context.get("goal", "")
        step = context.get("step", "")
        api_key_set = bool(os.getenv(self.profile.transport.api_key_env, ""))

        prompt_tokens_est = self._estimate_tokens(prompt)
        self._trace(
            self.profile.paths.prompt_trace_file,
            {
                "profile": self.active_profile_name,
                "provider": self.profile.provider,
                "model": self.profile.model,
                "endpoint": f"{self.profile.transport.base_url}{self.profile.transport.api_path}",
                "goal": goal,
                "step": step,
                "api_key_set": api_key_set,
                "prompt_length": len(prompt),
                "prompt_tokens_est": prompt_tokens_est,
            },
        )

        response = (
            f"[model:{self.profile.model}] "
            f"goal={goal} | step={step} | provider={self.profile.provider} "
            f"| endpoint={self.profile.transport.base_url}{self.profile.transport.api_path} "
            f"| advice=保持目标一致并执行可验证动作"
        )

        response_tokens_est = self._estimate_tokens(response)
        self._trace(
            self.profile.paths.response_trace_file,
            {
                "profile": self.active_profile_name,
                "model": self.profile.model,
                "response": response,
                "response_tokens_est": response_tokens_est,
                "total_tokens_est": prompt_tokens_est + response_tokens_est,
            },
        )
        return response

    def check_connection(self) -> Dict[str, Any]:
        endpoint = f"{self.profile.transport.base_url}{self.profile.transport.api_path}"
        if self.profile.provider == "mock":
            return {
                "ok": True,
                "provider": self.profile.provider,
                "model": self.profile.model,
                "endpoint": endpoint,
                "detail": "mock provider enabled",
            }

        try:
            req = Request(self.profile.transport.base_url, method="GET")
            with urlopen(req, timeout=self.profile.timeout_sec):
                pass
            return {
                "ok": True,
                "provider": self.profile.provider,
                "model": self.profile.model,
                "endpoint": endpoint,
                "detail": "endpoint reachable",
            }
        except URLError as exc:
            return {
                "ok": False,
                "provider": self.profile.provider,
                "model": self.profile.model,
                "endpoint": endpoint,
                "detail": f"endpoint unreachable: {exc}",
            }
