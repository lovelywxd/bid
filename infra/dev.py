"""Foreground local app + worker. Ctrl-C shuts both down, retaining data."""
import argparse
import os
import signal
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres", action="store_true", help="Use isolated project PostgreSQL on port 55432")
    args = parser.parse_args()
    env = {**os.environ, "BID_RUNTIME_MODE": "fixture"}
    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    pg_started = False
    pg_bin = ROOT / ".tools/node_modules/@embedded-postgres/darwin-arm64/native/bin"
    cluster = data / "postgres"
    children = []
    try:
        if args.postgres:
            if not (cluster / "PG_VERSION").exists():
                if cluster.exists() and any(cluster.iterdir()):
                    raise SystemExit("Refusing to initialize a nonempty PostgreSQL directory")
                subprocess.run([pg_bin / "initdb", "-D", cluster, "-U", "bid_agent", "--auth=trust"], check=True)
            status = subprocess.run([pg_bin / "pg_ctl", "-D", cluster, "status"], capture_output=True)
            if status.returncode:
                subprocess.run([pg_bin / "pg_ctl", "-D", cluster, "-l", data / "postgres.log",
                                "-o", "-h 127.0.0.1 -p 55432 -k /tmp", "start"], check=True)
                pg_started = True
            env["BID_DATABASE_URL"] = "postgresql+psycopg://bid_agent@127.0.0.1:55432/postgres"
        subprocess.run([ROOT / "backend/.venv/bin/alembic", "-c", ROOT / "backend/alembic.ini", "upgrade", "head"],
                       cwd=ROOT, env=env, check=True)
        python = str(ROOT / "backend/.venv/bin/python")
        children.append(subprocess.Popen([python, "-m", "uvicorn", "app.api:app", "--host", "127.0.0.1",
                                         "--port", "8765"], cwd=ROOT / "backend", env=env, start_new_session=True))
        # Worker checks the same DB; HTTP startup failures remain explicit uncertain activities.
        import urllib.request
        for _ in range(50):
            if children[0].poll() is not None:
                raise SystemExit("API exited; another local process may own port 8765")
            try:
                with urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=1):
                    break
            except OSError:
                time.sleep(.1)
        else:
            raise SystemExit("API health check timed out")
        children.append(subprocess.Popen([python, "-m", "app.execution"], cwd=ROOT / "backend", env=env,
                                         start_new_session=True))
        print("标书工作台 http://127.0.0.1:8765 / fixture only / Ctrl-C to stop", flush=True)
        while all(p.poll() is None for p in children):
            time.sleep(.5)
    except KeyboardInterrupt:
        pass
    finally:
        for p in reversed(children):
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)
                try:
                    p.wait(timeout=7)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
                    p.wait()
        if pg_started:
            subprocess.run([pg_bin / "pg_ctl", "-D", cluster, "stop", "-m", "fast"], check=True)


if __name__ == "__main__":
    main()
