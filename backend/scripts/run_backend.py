"""Launch with the project environment and a psycopg-compatible Windows loop."""
import asyncio
import os
import sys
from pathlib import Path


def _use_project_environment():
    # Respect an explicitly activated environment. A bare system Python should
    # use the installed project dependencies rather than global site-packages.
    if sys.prefix != sys.base_prefix:
        return
    backend = Path(__file__).resolve().parents[1]
    relative_python = Path("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    for directory in (backend.parent, backend):
        python = directory / ".venv" / relative_python
        if python.is_file():
            print(f"Using project Python: {python}", flush=True)
            os.execv(str(python), [str(python), "-m", "scripts.run_backend", *sys.argv[1:]])
            return


def main():
    _use_project_environment()
    import uvicorn

    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=8000))
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else asyncio.new_event_loop
    with asyncio.Runner(loop_factory=factory) as runner:
        runner.run(server.serve())


if __name__ == "__main__":
    main()
