"""One-time setup on a new machine (Windows, macOS or Linux). Safe to run again.

  python tools/bootstrap.py                      detect FilmCraft, create .venv, write config.local.json
  python tools/bootstrap.py --app PATH --cli PATH   point at a FilmCraft install it did not find
  python tools/bootstrap.py --lang en --model medium   transcript defaults for bin/index-footage
  python tools/bootstrap.py --minimal            skip the indexing packages (editing tools need none)
  python tools/bootstrap.py --mcp                also register the FilmCraft MCP server in .mcp.json

Run it with the Python you want the project to use (3.10 or newer); on Windows use "py tools\\bootstrap.py".
"""

import argparse
import json
import shutil
import subprocess
import sys
import venv
from pathlib import Path

import craft
from start_apps import ensure_token

ROOT = craft.ROOT
VENV = ROOT / ".venv"
FOLDERS = ("footage", "script", "index", "edit", "logs", "backup")
FFMPEG_HINT = {
    "win32": "winget install --id Gyan.FFmpeg -e   (then open a new terminal)",
    "darwin": "brew install ffmpeg",
}


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if craft.WINDOWS else "bin/python")


def setup_venv(minimal: bool) -> None:
    if not venv_python().exists():
        print(f"creating {VENV.name} ...")
        venv.EnvBuilder(with_pip=True).create(VENV)
    if minimal:
        return
    print("installing indexing packages (PySceneDetect, OpenCV, faster-whisper); this takes a few minutes ...")
    subprocess.run([str(venv_python()), "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)
    subprocess.run([str(venv_python()), "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")], check=True)


def write_mcp(python: Path) -> None:
    path = ROOT / ".mcp.json"
    data = craft.load_json(path, {})
    data.setdefault("mcpServers", {})["filmcraft"] = {
        "command": str(python),
        "args": [str(ROOT / "tools" / "fc_mcp.py")],
        "env": {"PYTHONUTF8": "1"},
    }
    craft.save_json(path, data)
    print(f"registered the filmcraft MCP server in {path.name} (Claude Code asks to approve it once)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app", help="FilmCraft desktop executable (macOS: .../FilmCraft.app/Contents/MacOS/FilmCraft)")
    ap.add_argument("--cli", help="filmcraft-cli executable")
    ap.add_argument("--port", type=int, help="control port (default 9876)")
    ap.add_argument("--project", help="FilmCraft project to open (default edit/main.fcproj)")
    ap.add_argument("--footage", help="footage folder, may be outside the repository (default footage/)")
    ap.add_argument("--lang", help="transcript language: vi, en, ... or auto")
    ap.add_argument("--model", help="faster-whisper model: small, medium, large-v3")
    ap.add_argument("--device", choices=["auto", "cpu", "cuda"], help="transcription device")
    ap.add_argument("--minimal", action="store_true", help="do not install the indexing packages")
    ap.add_argument("--mcp", action="store_true", help="write .mcp.json for the FilmCraft MCP server")
    args = ap.parse_args()

    if sys.version_info < (3, 10):
        print("Python 3.10 or newer is needed", file=sys.stderr)
        return 1

    setup_venv(args.minimal)

    cfg = craft.load_json(craft.CONFIG_FILE, {})
    app = Path(args.app) if args.app else craft.find_app()
    cli = Path(args.cli) if args.cli else craft.find_cli()
    for key, found in (("filmcraft_app", app), ("filmcraft_cli", cli)):
        if found and found.is_file():
            cfg[key] = str(found.resolve())
        else:
            cfg.pop(key, None)
    for key, value in (("control_port", args.port), ("project", args.project), ("footage_dir", args.footage)):
        if value is not None:
            cfg[key] = value
    whisper = cfg.setdefault("whisper", {"lang": "auto", "model": "small", "device": "auto"})
    for key in ("lang", "model", "device"):
        if getattr(args, key):
            whisper[key] = getattr(args, key)
    craft.save_json(craft.CONFIG_FILE, cfg)

    for name in FOLDERS:
        (ROOT / name).mkdir(exist_ok=True)
    ensure_token(rotate=False)
    if args.mcp:
        write_mcp(venv_python() if venv_python().exists() else Path(sys.executable))

    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    print()
    print(f"config:      {craft.CONFIG_FILE.name}")
    print(f"FilmCraft:   {cfg.get('filmcraft_app', 'NOT FOUND: pass --app PATH')}")
    print(f"CLI:         {cfg.get('filmcraft_cli', 'NOT FOUND: pass --cli PATH')}")
    print(f"token file:  {craft.TOKEN_FILE}")
    print(f"transcripts: {json.dumps(whisper)}")
    if missing:
        hint = FFMPEG_HINT.get(sys.platform, "sudo apt install ffmpeg")
        print(f"missing:     {', '.join(missing)} (install: {hint})")
    ok = "filmcraft_app" in cfg and "filmcraft_cli" in cfg and not missing
    print("\nnext: bin/start-apps, then open Claude Code in this folder" if ok else "\nfix the lines above, then run this again")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
