"""Run tests in a newly created disposable DB; never initialize the application DB."""
import argparse
import os
import socket
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg


def main(pg_bin):
    root = Path(__file__).resolve().parents[2] / "tmp" / ("qwen-postgres-" + uuid4().hex[:12])
    root.mkdir(parents=True)
    cluster = root / "cluster"
    suffix = ".exe" if os.name == "nt" else ""
    initdb, pg_ctl = Path(pg_bin) / ("initdb" + suffix), Path(pg_bin) / ("pg_ctl" + suffix)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    target = f"postgresql://postgres@127.0.0.1:{port}/postgres"
    started = False
    def command(args):
        # A background postmaster can inherit pipe handles on Windows; use a file.
        with (root / "commands.log").open("ab") as log:
            return subprocess.run([str(a) for a in args], check=True, stdout=log, stderr=log,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        command([initdb, "-D", cluster, "-U", "postgres", "-A", "trust", "--encoding=UTF8", "--no-locale"])
        command([pg_ctl, "-D", cluster, "-l", root / "server.log", "-o", f"-h 127.0.0.1 -p {port}", "-w", "start"])
        started = True
        with psycopg.connect(target) as conn:
            assert conn.info.port == port and conn.info.dbname == "postgres"
            conn.execute(Path("database/init.sql").read_text(encoding="utf-8"))
            for migration in sorted(Path("database/migrations").glob("*.sql")):
                conn.execute(migration.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO app_users (id,uid,username,email,password_hash,role) "
                         "VALUES (%s,'00000','isolated-test-user','isolated@example.test','unused','user')",
                         (uuid4(),))
        env = {**os.environ, "TEST_DATABASE_URL": target, "PYTHONUTF8": "1"}
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rs"], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
        report = Path("eval-results/qwen-upgrade/pytest-postgres.txt")
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(result.stdout, encoding="utf-8")
        print(result.stdout[-6000:])
        return result.returncode
    finally:
        if started:
            command([pg_ctl, "-D", cluster, "-m", "fast", "-w", "stop"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", default=r"C:\Program Files\PostgreSQL\18\bin")
    raise SystemExit(main(parser.parse_args().pg_bin))
