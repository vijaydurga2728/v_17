"""Rewrite the MT5_LOGIN line in .env to 53143050. Leaves all other lines (password, server, symbol, timeout) untouched.

Usage:
  .venv\\Scripts\\python.exe scripts\\fix_env_login.py 53143050
"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python fix_env_login.py <NEW_LOGIN>")
        return 1
    new_login = sys.argv[1]
    if not new_login.isdigit():
        print(f"login must be digits, got {new_login!r}")
        return 1

    env = Path(".env")
    if not env.exists():
        print("no .env found in cwd")
        return 1

    raw = env.read_text(encoding="utf-8")
    lines = raw.splitlines()
    new_lines: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith("MT5_LOGIN="):
            new_lines.append(f"MT5_LOGIN={new_login}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.insert(0, f"MT5_LOGIN={new_login}")

    env.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"MT5_LOGIN set to {new_login} in {env.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
