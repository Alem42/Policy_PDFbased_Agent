"""Run one native API process; use different ports for a multi-instance demo."""

import argparse
import asyncio
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    # Psycopg async checkpointers need SelectorEventLoop on Windows. This runner
    # also deliberately avoids development reload when measuring concurrency.
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else asyncio.new_event_loop
    with asyncio.Runner(loop_factory=factory) as runner:
        server = uvicorn.Server(
            uvicorn.Config("app.main:app", host=args.host, port=args.port, log_level="info")
        )
        runner.run(server.serve())


if __name__ == "__main__":
    main()
