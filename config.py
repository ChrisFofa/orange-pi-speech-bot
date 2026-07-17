"""
config.py

Reusable configuration loader for Big Bang special event packages.

Purpose
-------
This file centralizes environment-variable loading and basic runtime settings.

Future special event developers should be able to copy this file unchanged
into new event packages.

Security rules
--------------
This config file must never contain private secrets directly.

Allowed on Orange Pi / package:
    - SUPABASE_URL
    - SUPABASE_PUBLISHABLE_KEY
    - SUPABASE_ANON_KEY, if using legacy Supabase keys

Not allowed in event package:
    - SUPABASE_SERVICE_ROLE_KEY
    - SUPABASE_SECRET_KEY
    - private AI API keys
    - production admin tokens

The app can read a publishable/anon Supabase key because it is a low-privilege
client key. Any privileged action must be enforced by Supabase RLS, RPC
functions, or backend-only code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


# ------------------------------------------------------------
# Basic .env loading
# ------------------------------------------------------------

def _manual_load_dotenv(env_path: Path) -> None:
    """
    Small fallback .env parser.

    We use python-dotenv when available, but this fallback keeps the app
    from crashing if python-dotenv is missing before setup is complete.

    This parser intentionally supports only simple KEY=VALUE lines.
    """
    if not env_path.exists():
        return

    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return

    for raw_line in lines:
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        # Do not overwrite environment variables already provided by the OS.
        os.environ.setdefault(key, value)


def load_environment_files(start_dir: Optional[Path] = None) -> List[Path]:
    """
    Load environment files from common Big Bang locations.

    Search order:
        1. event folder .env
        2. ~/bigbang/.env
        3. ~/.bigbang/.env

    Returns a list of files that existed and were attempted.
    """
    if start_dir is None:
        start_dir = Path(__file__).resolve().parent

    candidate_paths = [
        Path("/etc/bigbang.env"),
        Path("/opt/bigbang/.env"),
        Path("/opt/bigbang/app/.env"),
        start_dir / ".env",
        Path.home() / "bigbang" / ".env",
        Path.home() / ".bigbang" / ".env",
    ]

    loaded_files: List[Path] = []

    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        load_dotenv = None

    for env_path in candidate_paths:
        if not env_path.exists():
            continue

        loaded_files.append(env_path)

        if load_dotenv is not None:
            load_dotenv(dotenv_path=env_path, override=False)
        else:
            _manual_load_dotenv(env_path)

    return loaded_files


# ------------------------------------------------------------
# Environment variable helpers
# ------------------------------------------------------------

def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Read an environment variable.

    Blank strings are treated as missing.
    """
    value = os.environ.get(name)

    if value is None:
        return default

    value = value.strip()

    if value == "":
        return default

    return value


def get_bool_env(name: str, default: bool = False) -> bool:
    """
    Read a boolean environment variable.

    True values:
        1, true, yes, y, on

    False values:
        0, false, no, n, off
    """
    value = get_env(name)

    if value is None:
        return default

    normalized = value.lower().strip()

    if normalized in {"1", "true", "yes", "y", "on"}:
        return True

    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    return default


def mask_secret(value: Optional[str], visible_start: int = 6, visible_end: int = 4) -> str:
    """
    Mask a secret-like value for safe logs.

    Example:
        abcdef1234567890 -> abcdef******7890
    """
    if not value:
        return "<missing>"

    if len(value) <= visible_start + visible_end:
        return "*" * len(value)

    return f"{value[:visible_start]}{'*' * 8}{value[-visible_end:]}"


# ------------------------------------------------------------
# Main app config object
# ------------------------------------------------------------

@dataclass(frozen=True)
class AppConfig:
    """
    Runtime config for the special event app.
    """

    event_code: str

    supabase_url: Optional[str]
    supabase_key: Optional[str]

    kiosk_fullscreen: bool
    allow_escape: bool
    validate_on_launch: bool

    rpc_validate_event_code: str
    rpc_get_package: str
    rpc_get_ai_credentials: str
    rpc_register_event_launch: str

    events_dir: Path

    loaded_env_files: List[Path]

    @property
    def has_supabase_config(self) -> bool:
        """
        Returns True if the app has enough config to call Supabase.
        """
        return bool(self.supabase_url and self.supabase_key)

    @property
    def safe_debug_summary(self) -> Dict[str, str]:
        """
        Safe-to-print config summary.

        This masks the Supabase key so logs do not expose it.
        """
        return {
            "event_code": self.event_code,
            "supabase_url": self.supabase_url or "<missing>",
            "supabase_key": mask_secret(self.supabase_key),
            "kiosk_fullscreen": str(self.kiosk_fullscreen),
            "allow_escape": str(self.allow_escape),
            "validate_on_launch": str(self.validate_on_launch),
            "rpc_validate_event_code": self.rpc_validate_event_code,
            "rpc_get_package": self.rpc_get_package,
            "rpc_get_ai_credentials": self.rpc_get_ai_credentials,
            "rpc_register_event_launch": self.rpc_register_event_launch,
            "events_dir": str(self.events_dir),
            "loaded_env_files": ", ".join(str(p) for p in self.loaded_env_files) or "<none>",
        }


def load_app_config(
    event_code_default: str = "DEMO1",
    start_dir: Optional[Path] = None,
) -> AppConfig:
    """
    Load app config from environment variables.

    Environment variable priority:
        1. Real OS environment variables
        2. event folder .env
        3. ~/bigbang/.env
        4. ~/.bigbang/.env
        5. built-in defaults
    """
    if start_dir is None:
        start_dir = Path(__file__).resolve().parent

    loaded_env_files = load_environment_files(start_dir)

    # Support both new and legacy Supabase key names.
    supabase_key = (
        get_env("SUPABASE_PUBLISHABLE_KEY")
        or get_env("SUPABASE_ANON_KEY")
        or get_env("SUPABASE_KEY")
    )

    events_dir_raw = get_env(
        "BIGBANG_EVENTS_DIR",
        str(Path.home() / "bigbang" / "events"),
    )

    return AppConfig(
        event_code=get_env("BIGBANG_EVENT_CODE", event_code_default) or event_code_default,

        supabase_url=get_env("SUPABASE_URL"),
        supabase_key=supabase_key,

        kiosk_fullscreen=get_bool_env("BIGBANG_KIOSK_FULLSCREEN", True),
        allow_escape=get_bool_env("BIGBANG_ALLOW_ESCAPE", True),
        validate_on_launch=get_bool_env("BIGBANG_VALIDATE_ON_LAUNCH", False),

        rpc_validate_event_code=get_env(
            "BIGBANG_RPC_VALIDATE_EVENT_CODE",
            "validate_event_code",
        ) or "validate_event_code",

        rpc_get_package=get_env(
            "BIGBANG_RPC_GET_PACKAGE",
            "get_special_event_package",
        ) or "get_special_event_package",

        rpc_get_ai_credentials=get_env(
            "BIGBANG_RPC_GET_AI_CREDENTIALS",
            "get_event_ai_credentials",
        ) or "get_event_ai_credentials",

        rpc_register_event_launch=get_env(
            "BIGBANG_RPC_REGISTER_EVENT_LAUNCH",
            "register_event_launch",
        ) or "register_event_launch",

        events_dir=Path(events_dir_raw).expanduser(),

        loaded_env_files=loaded_env_files,
    )


def validate_supabase_config(config: AppConfig) -> List[str]:
    """
    Return a list of config problems related to Supabase.

    This does not raise by itself because the demo screen can run without
    Supabase. Future events can choose to make Supabase required.
    """
    problems: List[str] = []

    if not config.supabase_url:
        problems.append("SUPABASE_URL is missing.")

    if not config.supabase_key:
        problems.append(
            "SUPABASE_PUBLISHABLE_KEY, SUPABASE_ANON_KEY, or SUPABASE_KEY is missing."
        )

    if config.supabase_url and not config.supabase_url.startswith("https://"):
        problems.append("SUPABASE_URL should usually start with https://.")

    return problems