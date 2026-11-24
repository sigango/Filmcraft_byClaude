# Setup on Windows, macOS, and Linux

This guide installs the tools, connects them to FilmCraft, and opens a first Claude Code session. It takes about 15 minutes, most of it downloads.

## Requirements

| | Windows 10/11 | macOS 12 or newer | Linux |
|---|---|---|---|
| FilmCraft app and `filmcraft-cli` | `filmcraft-<ver>-windows-x64.msi` (or `arm64`); installs both executables in `%LOCALAPPDATA%\Programs\ArtCraft\FilmCraft` | `filmcraft-<ver>-macos-universal.dmg` (app) and `filmcraft-cli-<ver>-macos-universal.zip` (CLI, a separate download) | `.deb`, `.rpm`, or the tarball; the CLI is included |
| Python 3.10 or newer | `winget install Python.Python.3.12` or python.org | `brew install python` or python.org | system package |
| ffmpeg and ffprobe on `PATH` | `winget install --id Gyan.FFmpeg -e` | `brew install ffmpeg` | `sudo apt install ffmpeg` |
| Git | Git for Windows (Claude Code runs its shell commands in Git Bash) | Xcode command-line tools or `brew install git` | system package |
| Claude Code | [install guide](https://docs.claude.com/en/docs/claude-code/setup) | same | same |

FilmCraft downloads are on the [releases page](https://github.com/storytold/filmcraft/releases/latest). The tools were tested with FilmCraft 0.20.1.

On macOS, drag `FilmCraft.app` to `/Applications` and unzip the CLI to `/usr/local/bin`, `/opt/homebrew/bin`, or `~/.local/bin`. Any other place works if you pass its path to the setup script.

## 1. Clone the repository

```bash
git clone https://github.com/sigango/Filmcraft_byClaude.git
cd Filmcraft_byClaude
```

## 2. Run the setup script

macOS and Linux:

```bash
python3 tools/bootstrap.py --lang en
```

Windows (PowerShell or cmd):

```powershell
py tools\bootstrap.py --lang en
```

Set `--lang` to the language spoken in your footage (`vi`, `en`, `ja`, ...) or `auto`. The script:

- creates `.venv/` and installs the indexing packages from `requirements.txt` (a few minutes; `--minimal` skips them if you will not index footage);
- finds the FilmCraft app and CLI in their usual install folders and writes their paths to `config.local.json`;
- creates the control token in a private file (`~/.config/filmcraft-agent/token` on macOS and Linux, `%APPDATA%\filmcraft-agent\token` on Windows);
- creates the working folders `footage/`, `script/`, `index/`, `edit/`, `logs/`, and `backup/`;
- checks that ffmpeg and ffprobe are on `PATH`.

If it reports `NOT FOUND`, pass the paths yourself and run it again:

```powershell
py tools\bootstrap.py --app "D:\Apps\FilmCraft\filmcraft.exe" --cli "D:\Apps\FilmCraft\filmcraft-cli.exe"
```

```bash
python3 tools/bootstrap.py --app /Applications/FilmCraft.app/Contents/MacOS/FilmCraft --cli ~/Downloads/filmcraft-cli
```

The script is safe to run again; it keeps the existing token and settings it was not asked to change.

## 3. Start FilmCraft

```bash
bin/start-apps
```

In cmd or PowerShell, use `bin\start-apps.cmd`. The expected output is `FilmCraft up on 9876`. FilmCraft opens `edit/main.fcproj` if it exists and an empty project otherwise. Run `bin/fc save` once to save the empty project as `edit/main.fcproj`, so later sessions reopen it.

Check the connection:

```bash
bin/fc ping
```

## 4. Add footage and the script

Copy or link your media into `footage/` (subfolders are fine) and the script into `script/` as plain text or Markdown. To keep media on another drive, see [customize.md](customize.md).

Index it once; reruns only process new files:

```bash
bin/index-footage
```

This writes `index/footage_index.md`, which Claude reads. The first transcript run downloads the Whisper model (about 600 MB for `small`).

## 5. Open Claude Code

```bash
claude
```

Claude Code loads `CLAUDE.md` and the permission rules in `.claude/settings.json` from this folder. A first request could be:

> Read script/script.md and the footage index, then build a first cut of about two minutes.

Then follow the loop in [workflow.md](workflow.md).

## Windows notes

- Claude Code on Windows runs commands in Git Bash, so it uses the same `bin/fc ...` commands as on macOS. The `.cmd` launchers are for running the tools yourself.
- PowerShell rewrites quotes inside JSON arguments. Prefer the `key=value` form, which needs no quoting: `bin\fc.cmd run playhead.set frame=50`.
- If FilmCraft opens and closes immediately, the FilmCraft README describes the `WGPU_BACKEND` workaround for some graphics drivers.

## Troubleshooting

| Message | Fix |
|---|---|
| `FilmCraft not found` | Run the setup script with `--app PATH` |
| `FilmCraft is not listening on 127.0.0.1:9876` | Run `bin/start-apps`; if another program uses the port, change it (see [customize.md](customize.md)) |
| `still starting` on the first command | Wait a second and repeat the command |
| `no active sequence` | Open or create a sequence in the app, or build one with `bin/cutlist ... --apply` |
| Authentication errors after `bin/start-apps --rotate` | Quit FilmCraft, run `bin/start-apps` again, and restart Claude Code |
