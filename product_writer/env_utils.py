from __future__ import annotations

import os
import shutil
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def ensure_env_file(root: Path) -> Path:
    env_path = root / ".env"
    example_path = root / ".env.example"
    if not env_path.exists() and example_path.exists():
        shutil.copyfile(example_path, env_path)
    return env_path


def load_environment(root: Path) -> None:
    env_path = ensure_env_file(root)
    if env_path.exists() and load_dotenv is not None:
        load_dotenv(env_path)
        return
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)


def get_deepseek_api_key(root: Path) -> str | None:
    load_environment(root)
    value = os.getenv("DEEPSEEK_API_KEY", "").strip()
    return value or None
