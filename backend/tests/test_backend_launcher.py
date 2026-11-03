from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import run_backend


@pytest.mark.parametrize("platform", ["win32", "linux"])
@pytest.mark.parametrize("location", ["root", "backend", "both", "none"])
def test_system_python_selects_existing_project_environment(
    monkeypatch, tmp_path, platform, location
):
    backend = tmp_path / "backend"
    monkeypatch.setattr(run_backend, "__file__", str(backend / "scripts" / "run_backend.py"))
    monkeypatch.setattr(run_backend.sys, "platform", platform)
    monkeypatch.setattr(run_backend.sys, "prefix", "system")
    monkeypatch.setattr(run_backend.sys, "base_prefix", "system")
    monkeypatch.setattr(run_backend.sys, "argv", ["run_backend.py"])
    relative = Path("Scripts/python.exe" if platform == "win32" else "bin/python")
    root_python = tmp_path / ".venv" / relative
    backend_python = backend / ".venv" / relative
    for path, selected in (
        (root_python, location in ("root", "both")),
        (backend_python, location in ("backend", "both")),
    ):
        if selected:
            path.parent.mkdir(parents=True)
            path.touch()
    execute = Mock()
    child = Mock()
    child.return_value.wait.return_value = 0
    monkeypatch.setattr(run_backend.os, "execv", execute)
    monkeypatch.setattr(run_backend.subprocess, "Popen", child)

    if location == "none":
        run_backend._use_project_environment()
        execute.assert_not_called()
        child.assert_not_called()
        return
    expected = str(backend_python if location == "backend" else root_python)
    args = [expected, "-m", "scripts.run_backend"]
    if platform == "win32":
        with pytest.raises(SystemExit):
            run_backend._use_project_environment()
        child.assert_called_once_with(args)
        execute.assert_not_called()
    else:
        run_backend._use_project_environment()
        execute.assert_called_once_with(expected, args)


def test_explicitly_activated_environment_is_not_overridden(monkeypatch):
    monkeypatch.setattr(run_backend.sys, "prefix", "custom-venv")
    monkeypatch.setattr(run_backend.sys, "base_prefix", "system")
    execute = Mock()
    monkeypatch.setattr(run_backend.os, "execv", execute)

    run_backend._use_project_environment()

    execute.assert_not_called()
