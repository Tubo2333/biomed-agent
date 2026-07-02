# config.py — Unified configuration loader
#
# Loads config.yaml, overrides with BIOMED_<SECTION>_<KEY> env vars.
# Import this module anywhere: from src.config import config

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load YAML config file. Returns {} if file not found."""
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _env_override(cfg: dict[str, Any], prefix: str = "BIOMED_") -> dict[str, Any]:
    """Override config values from environment variables.

    BIOMED_LLM_MODEL=claude-sonnet → cfg["llm"]["model"] = "claude-sonnet"
    BIOMED_API_PORT=9000            → cfg["api"]["port"] = 9000
    """
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        # BIOMED_LLM_MODEL → ["llm", "model"]
        parts = key[len(prefix):].lower().split("_", 1)
        if len(parts) != 2:
            continue
        section, subkey = parts
        if section in cfg and isinstance(cfg[section], dict):
            # Coerce to int/float if possible
            try:
                value = int(value)
            except (ValueError, TypeError):
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    pass
            cfg[section][subkey] = value
    return cfg


class _Config:
    """Singleton config object — attribute access via dot notation."""

    def __init__(self, data: dict[str, Any]):
        for key, value in data.items():
            if isinstance(value, dict):
                value = _Config(value)
            setattr(self, key, value)

    def __repr__(self) -> str:
        items = [f"{k}={v!r}" for k, v in self.__dict__.items()]
        return f"Config({', '.join(items)})"

    def get(self, key: str, default: Any = None) -> Any:
        return self.__dict__.get(key, default)


# ── Load and expose ───────────────────────────────────────────

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
_raw = _load_yaml(_CONFIG_PATH)
_raw = _env_override(_raw)
config = _Config(_raw)
