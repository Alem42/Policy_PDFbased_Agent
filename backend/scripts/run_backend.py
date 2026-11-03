"""Launch with the project environment and a psycopg-compatible Windows loop."""
import argparse
import asyncio
import os
import subprocess
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
            args = [str(python), "-m", "scripts.run_backend", *sys.argv[1:]]
            if sys.platform != "win32":
                os.execv(str(python), args)
                return
            # Windows execv starts a detached process and exits, so Ctrl+C and
            # process managers would lose the server. Run it as a child instead.
            child = subprocess.Popen(args)
            try:
                sys.exit(child.wait())
            except KeyboardInterrupt:
                sys.exit(child.wait())


def loop_factory(use_subprocess: bool = False):
    # Psycopg's async checkpointer cannot run on Windows' default Proactor loop.
    return asyncio.SelectorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="Restart when app/ changes")
    args = parser.parse_args()
    _use_project_environment()
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=["app"] if args.reload else None,
        loop="scripts.run_backend:loop_factory",
    )


if __name__ == "__main__":
    main()
