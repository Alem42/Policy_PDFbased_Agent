"""Fail at startup, not at the first model call, when the wrong Python runs the backend."""

import sys
from pathlib import Path

from app.core.config import BACKEND_ROOT, get_settings

PROJECT_VENVS = (BACKEND_ROOT.parent / ".venv", BACKEND_ROOT / ".venv")


def start_command() -> str:
    if sys.platform == "win32":
        return r"..\.venv\Scripts\python.exe -m scripts.run_backend"
    return "../.venv/bin/python -m scripts.run_backend"


def require_project_interpreter() -> None:
    if not get_settings().require_project_venv:
        return
    venvs = [path.resolve() for path in PROJECT_VENVS if path.is_dir()]
    # Containers and fresh checkouts install dependencies into their own interpreter.
    if not venvs or Path(sys.prefix).resolve() in venvs:
        return
    raise RuntimeError(
        f"The backend is running on {sys.executable}, not the project environment "
        f"{venvs[0]}. That interpreter may lack optional dependencies such as torch "
        f"for local Qwen models. Stop it and run from backend/: `{start_command()}` "
        "(add --reload while developing). Set REQUIRE_PROJECT_VENV=false only if this "
        "interpreter deliberately has every dependency installed."
    )
