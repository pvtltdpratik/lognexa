"""Agent configuration and persistent state (data directory, enrolment, checkpoints)."""

from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path


def default_data_dir() -> Path:
    env = os.environ.get("LOGNEXA_AGENT_DATA_DIR")
    if env:
        return Path(env)
    if platform.system() == "Windows":
        base = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        return base / "Lognexa" / "agent"
    # Unprivileged dev runs fall back to the user's home.
    if os.geteuid() == 0 if hasattr(os, "geteuid") else False:
        return Path("/var/lib/lognexa-agent")
    return Path.home() / ".lognexa-agent"


@dataclass
class AgentConfig:
    server_url: str
    data_dir: Path
    enroll_token: str | None = None
    verify_tls: bool | str = True  # True, False, or a path to a CA bundle
    poll_interval: float = 15.0
    heartbeat_interval: float = 60.0
    send_interval: float = 10.0
    batch_size: int = 500
    max_buffer_events: int = 200_000
    collectors: dict[str, bool] = field(default_factory=dict)
    log_level: str = "INFO"
    log_file: str | None = None  # also log here (rotating); needed when no console
    insecure_http_ok: bool = False  # allow plain http only for localhost dev

    @property
    def state_path(self) -> Path:
        return self.data_dir / "state.json"

    @property
    def buffer_path(self) -> Path:
        return self.data_dir / "buffer.db"

    @classmethod
    def load(cls, path: str | None = None) -> "AgentConfig":
        data: dict = {}
        cfg_path = Path(path) if path else (default_data_dir() / "config.json")
        if cfg_path.exists():
            # utf-8-sig: tolerate a BOM written by Windows PowerShell 5.1 or Notepad.
            data = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
        # Environment variables override the file.
        env = os.environ
        server = env.get("LOGNEXA_SERVER_URL", data.get("server_url", ""))
        if not server:
            raise SystemExit("server_url is required (set it in config.json or LOGNEXA_SERVER_URL)")
        data_dir = Path(env.get("LOGNEXA_AGENT_DATA_DIR", data.get("data_dir") or default_data_dir()))
        verify = data.get("verify_tls", True)
        if "LOGNEXA_AGENT_CA_BUNDLE" in env:
            verify = env["LOGNEXA_AGENT_CA_BUNDLE"]
        elif env.get("LOGNEXA_AGENT_INSECURE_TLS") == "1":
            verify = False
        return cls(
            server_url=server.rstrip("/"),
            data_dir=data_dir,
            enroll_token=env.get("LOGNEXA_ENROLL_TOKEN", data.get("enroll_token")),
            verify_tls=verify,
            poll_interval=float(data.get("poll_interval", 15.0)),
            heartbeat_interval=float(data.get("heartbeat_interval", 60.0)),
            send_interval=float(data.get("send_interval", 10.0)),
            batch_size=int(data.get("batch_size", 500)),
            max_buffer_events=int(data.get("max_buffer_events", 200_000)),
            collectors=data.get("collectors", {}),
            log_level=env.get("LOGNEXA_AGENT_LOG_LEVEL", data.get("log_level", "INFO")),
            log_file=env.get("LOGNEXA_AGENT_LOG_FILE", data.get("log_file")) or None,
            insecure_http_ok=bool(data.get("insecure_http_ok", False)) or env.get("LOGNEXA_AGENT_ALLOW_HTTP") == "1",
        )

    def collector_enabled(self, name: str) -> bool:
        return self.collectors.get(name, True)


class State:
    """Durable agent state: device credential and per-collector checkpoints."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict = {"device_uid": None, "credential": None, "checkpoints": {}}
        if path.exists():
            try:
                self.data.update(json.loads(path.read_text(encoding="utf-8-sig")))
            except (ValueError, OSError):
                pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        tmp.replace(self.path)
        if platform.system() != "Windows":
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass

    @property
    def enrolled(self) -> bool:
        return bool(self.data.get("credential") and self.data.get("device_uid"))

    @property
    def device_uid(self) -> str | None:
        return self.data.get("device_uid")

    @property
    def credential(self) -> str | None:
        return self.data.get("credential")

    def set_credential(self, device_uid: str, credential: str) -> None:
        self.data["device_uid"] = device_uid
        self.data["credential"] = credential
        self.save()

    def checkpoint(self, collector: str, default=None):
        return self.data.get("checkpoints", {}).get(collector, default)

    def set_checkpoint(self, collector: str, value) -> None:
        self.data.setdefault("checkpoints", {})[collector] = value
        self.save()


def is_privileged() -> bool:
    if platform.system() == "Windows":
        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return hasattr(os, "geteuid") and os.geteuid() == 0
