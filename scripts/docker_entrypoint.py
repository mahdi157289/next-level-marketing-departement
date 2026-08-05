"""Container entrypoint: migrate DB then exec the main command."""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> None:
    os.chdir("/app")
    if os.getenv("DATABASE_URL"):
        print("[entrypoint] alembic upgrade head...")
        subprocess.run(["alembic", "upgrade", "head"], check=True)
    if len(sys.argv) < 2:
        print("Usage: docker_entrypoint.py <command> [args...]", file=sys.stderr)
        sys.exit(2)
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
