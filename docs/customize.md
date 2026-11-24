# Customizing for your machine

All machine-specific settings live in `config.local.json` at the repository root. The setup script writes it, Git ignores it, and you can edit it by hand. Paths may be absolute or relative to the repository, and `~` and environment variables such as `%USERPROFILE%` are expanded.

## Settings

| Key | Default | Environment override | Purpose |
|---|---|---|---|
| `filmcraft_app` | detected | `FILMCRAFT_APP` | FilmCraft desktop executable (on macOS, the binary inside `FilmCraft.app/Contents/MacOS/`) |
| `filmcraft_cli` | detected | `FILMCRAFT_CLI` | `filmcraft-cli` executable |
| `control_port` | `9876` | `FILMCRAFT_CONTROL_PORT` | Local control port the app listens on |
| `token_file` | see below | `FILMCRAFT_TOKEN_FILE` | Private file holding the control token |
| `project` | `edit/main.fcproj` | `FILMCRAFT_PROJECT` | Project opened by `bin/start-apps` and saved by `bin/fc save` |
| `footage_dir` | `footage` | | Folder indexed by `bin/index-footage` when no folder is given |
| `whisper.lang` | `auto` | | Spoken language for transcripts (`vi`, `en`, ...) |
| `whisper.model` | `small` | | faster-whisper model: `small`, `medium`, `large-v3`, ... |
| `whisper.device` | `auto` | | `cpu`, `cuda` (NVIDIA GPU on Windows or Linux), or `auto` |

The token file defaults to `~/.config/filmcraft-agent/token` on macOS and Linux and `%APPDATA%\filmcraft-agent\token` on Windows. Keep it outside the repository: anyone with the token can control the app.

Example for a Windows machine with footage on a second drive:

```json
{
  "filmcraft_app": "C:/Users/me/AppData/Local/Programs/ArtCraft/FilmCraft/filmcraft.exe",
  "filmcraft_cli": "C:/Users/me/AppData/Local/Programs/ArtCraft/FilmCraft/filmcraft-cli.exe",
  "footage_dir": "E:/Shoots/2026-11-wedding",
  "project": "E:/Shoots/2026-11-wedding/edit.fcproj",
  "whisper": {"lang": "en", "model": "medium", "device": "cuda"}
}
```

Most settings can also be passed to the setup script: `--app`, `--cli`, `--port`, `--project`, `--footage`, `--lang`, `--model`, and `--device`.

## Footage outside the repository

Set `footage_dir`, or pass a folder to `bin/index-footage /path/to/media`. Files inside the repository are indexed with relative paths and files elsewhere with absolute paths, so a cutlist works either way. Names starting with `_` or `.` are skipped, which is a convenient way to keep test clips or rejects out of the index.

## Transcription

- Choose the model by accuracy and speed: `small` is the default, while `medium` and `large-v3` are more accurate and slower. Models download once to the Hugging Face cache.
- `--device cuda` (or `whisper.device: "cuda"`) runs on an NVIDIA GPU with float16 on Windows and Linux; on macOS transcription runs on the CPU.
- `bin/index-footage --no-whisper` indexes scenes only, and `--threshold` tunes scene detection (lower values find more cuts).

## Several projects

Use one clone per film, or keep one clone and switch projects with the environment:

```bash
FILMCRAFT_PROJECT=edit/trailer.fcproj bin/start-apps
```

In PowerShell: `$env:FILMCRAFT_PROJECT = "edit\trailer.fcproj"; bin\start-apps.cmd`.

## Permissions

`.claude/settings.json` lets Claude Code run the four `bin/` tools without asking each time. Other commands still ask. Add personal rules to `.claude/settings.local.json`, which stays on your machine.

## MCP server

FilmCraft ships an MCP server with 17 tools, including screenshots and UI clicks. The `bin/fc` commands cover everyday editing at a fraction of the context cost (see [token-cost.md](token-cost.md)), so the setup script registers the server only when asked:

```bash
python3 tools/bootstrap.py --mcp
```

This writes `.mcp.json` with this machine's paths. The token stays in its private file; `tools/fc_mcp.py` reads it and passes it to `filmcraft-cli` through the environment. Delete the `filmcraft` entry from `.mcp.json` to turn the server off again.

## Adding a tool

Write `tools/my_tool.py`, then copy any launcher to `bin/my-tool` and `bin/my-tool.cmd`. Each launcher runs the Python file named after itself, with dashes turned into underscores, using the project's `.venv`. Import `craft` for the control connection, configuration, and time conversion:

```python
import craft

fc = craft.filmcraft()
seq = fc.run("sequence.inspect")
print(craft.summarize_sequence(seq))
```

Add a permission rule for it in `.claude/settings.json` and a line in `CLAUDE.md` so Claude knows when to use it.
