"""MCP server for Claude Code, bridged to the running FilmCraft app.

.mcp.json starts this script; it reads the token from its private file and hands it to
filmcraft-cli through the environment, so the token never sits in .mcp.json.
"""

import os
import subprocess
import sys

import craft


def main() -> int:
    token = craft.fc_token()
    cli = craft.find_cli()
    if not token or cli is None:
        print("filmcraft MCP: run python tools/bootstrap.py and bin/start-apps first", file=sys.stderr)
        return 1
    env = {**os.environ, "FILMCRAFT_CONTROL_TOKEN": token}
    argv = [str(cli), "mcp", "--bridge", f"127.0.0.1:{craft.FC_PORT}"]
    if craft.WINDOWS:
        # os.exec* on Windows spawns a child and exits, which would close the MCP stdio pipe.
        return subprocess.call(argv, env=env)
    os.execve(argv[0], argv, env)


if __name__ == "__main__":
    sys.exit(main())
