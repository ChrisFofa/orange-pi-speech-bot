"""
event_runtime.py

Reusable event runtime loader for Big Bang special event packages.

Purpose
-------
This file gives every event a consistent startup style.

It:
    - finds the event root folder,
    - loads event.json,
    - validates required manifest fields,
    - loads config,
    - detects the device MAC address,
    - optionally creates a Supabase client.

Future event developers should copy this file into new event packages
and usually leave it unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import AppConfig, load_app_config, validate_supabase_config
from device_utils import get_device_mac
from supabase_helper import BigBangSupabaseClient


# ------------------------------------------------------------
# Manifest helpers
# ------------------------------------------------------------

REQUIRED_EVENT_JSON_FIELDS = [
    "schema_version",
    "event_code",
    "event_name",
    "event_version",
    "entrypoint",
]


def get_event_root() -> Path:
    """
    Return the folder containing this event package.

    Since this file lives at the package root, its parent folder is the event root.
    """
    return Path(__file__).resolve().parent


def get_event_manifest_path(event_root: Optional[Path] = None) -> Path:
    """
    Return the expected event.json path.
    """
    if event_root is None:
        event_root = get_event_root()

    return event_root / "event.json"


def load_event_manifest(event_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load event.json from the event root.
    """
    manifest_path = get_event_manifest_path(event_root)

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"event.json not found at expected path: {manifest_path}"
        )

    try:
        with manifest_path.open("r", encoding="utf-8") as file_handle:
            data = json.load(file_handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"event.json is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("event.json must contain a JSON object at the top level.")

    return data


def validate_event_manifest(manifest: Dict[str, Any]) -> List[str]:
    """
    Validate required event.json fields.

    Returns a list of problems. Empty list means valid enough to run.
    """
    problems: List[str] = []

    for field in REQUIRED_EVENT_JSON_FIELDS:
        if field not in manifest:
            problems.append(f"event.json is missing required field: {field}")

    event_code = str(manifest.get("event_code", "")).strip()

    if not event_code:
        problems.append("event.json field event_code is blank.")

    if " " in event_code:
        problems.append("event_code should not contain spaces.")

    entrypoint = manifest.get("entrypoint")

    if not isinstance(entrypoint, dict):
        problems.append("event.json field entrypoint must be an object.")
    else:
        if not entrypoint.get("main_python_file"):
            problems.append("entrypoint.main_python_file is missing.")

        if not entrypoint.get("setup_script"):
            problems.append("entrypoint.setup_script is missing.")

        if not entrypoint.get("run_script"):
            problems.append("entrypoint.run_script is missing.")

    return problems


# ------------------------------------------------------------
# Event context
# ------------------------------------------------------------

@dataclass
class EventContext:
    """
    Runtime context passed around by the event app.

    This avoids future event developers needing to repeatedly load files,
    environment variables, or device identifiers.
    """

    event_root: Path
    manifest: Dict[str, Any]
    config: AppConfig
    device_mac: str

    @property
    def event_code(self) -> str:
        return str(self.manifest.get("event_code", self.config.event_code))

    @property
    def event_name(self) -> str:
        return str(self.manifest.get("event_name", "Unnamed Event"))

    @property
    def event_version(self) -> str:
        return str(self.manifest.get("event_version", "0.0.0"))

    def safe_summary(self) -> Dict[str, str]:
        """
        Return a safe-to-print summary.
        """
        return {
            "event_root": str(self.event_root),
            "event_code": self.event_code,
            "event_name": self.event_name,
            "event_version": self.event_version,
            "device_mac": self.device_mac,
            "supabase_configured": str(self.config.has_supabase_config),
        }


def build_event_context(require_supabase: bool = False) -> EventContext:
    """
    Build the standard event runtime context.

    Args:
        require_supabase:
            If True, this function raises an error when Supabase config is missing.
            For the demo screen, keep this False so Hello World can run offline.
    """
    event_root = get_event_root()
    manifest = load_event_manifest(event_root)

    manifest_problems = validate_event_manifest(manifest)

    if manifest_problems:
        joined = "\n".join(f"- {problem}" for problem in manifest_problems)
        raise ValueError(f"event.json validation failed:\n{joined}")

    event_code_default = str(manifest.get("event_code", "DEMO1"))

    config = load_app_config(
        event_code_default=event_code_default,
        start_dir=event_root,
    )

    if require_supabase:
        supabase_problems = validate_supabase_config(config)

        if supabase_problems:
            joined = "\n".join(f"- {problem}" for problem in supabase_problems)
            raise ValueError(f"Supabase config validation failed:\n{joined}")

    device_mac = get_device_mac()

    return EventContext(
        event_root=event_root,
        manifest=manifest,
        config=config,
        device_mac=device_mac,
    )


def create_supabase_client(context: EventContext) -> Optional[BigBangSupabaseClient]:
    """
    Create a Supabase client if config is available.

    Returns None if Supabase config is missing.
    """
    if not context.config.has_supabase_config:
        return None

    return BigBangSupabaseClient(
        supabase_url=context.config.supabase_url or "",
        supabase_key=context.config.supabase_key or "",
    )