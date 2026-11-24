"""Start FilmCraft with its control port open and the project loaded.

  bin/start-apps             start FilmCraft unless it is already listening
  bin/start-apps --rotate    make a new control token first (restart FilmCraft and Claude Code after)
  bin/start-apps --empty     open an empty project instead of the configured one

The token is created once and kept in a private file outside the repository; the app gets it
through its environment, so it never appears on a command line or in a config file.
"""

import argparse
import os
import secrets
import subprocess
import sys

import craft


def ensure_token(rotate: bool) -> str:
    path = craft.TOKEN_FILE
    if rotate and path.exists():
        path.unlink()
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        path.parent.mkdir(parents=True, exist_ok=True)
        token = secrets.token_hex(32)
        if craft.WINDOWS:
            # %APPDATA% is readable only by its owner, so no extra ACL is needed.
            path.write_text(token + "\n", encoding="utf-8")
        else:
            os.chmod(path.parent, 0o700)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(token + "\n")
        print(f"new FilmCraft token in {path}")
    return craft.fc_token()


def launch(app, args, env, log):
    if craft.WINDOWS:
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([str(app), *args], env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                         creationflags=flags, close_fds=True)
    else:
        subprocess.Popen([str(app), *args], env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                         start_new_session=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rotate", action="store_true")
    ap.add_argument("--empty", action="store_true")
    args = ap.parse_args()

    token = ensure_token(args.rotate)
    port = craft.FC_PORT
    if craft.port_open(port):
        print(f"FilmCraft already listening on {port}")
        if args.rotate:
            print("it still uses the old token: quit FilmCraft and run bin/start-apps again")
        return 0
    app = craft.find_app()
    if app is None or not app.exists():
        print("FilmCraft not found: install it or set filmcraft_app in config.local.json "
              "(python tools/bootstrap.py --app PATH)", file=sys.stderr)
        return 1
    project = craft.EDIT_PROJECT
    app_args = ["--control", str(port)] + ([str(project)] if project.exists() and not args.empty else ["--empty"])
    env = {**os.environ, "FILMCRAFT_CONTROL_TOKEN": token}
    log_path = craft.ROOT / "logs" / "filmcraft.log"
    log_path.parent.mkdir(exist_ok=True)
    with open(log_path, "ab") as log:
        launch(app, app_args, env, log)
    if craft.wait_port(port, 60):
        print(f"FilmCraft up on {port}" + (f" with {project.name}" if "--empty" not in app_args else ""))
        return 0
    print(f"FilmCraft did not open port {port}; see {log_path}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
