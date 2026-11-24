# FilmCraft by Claude

Claude Code edits a film in [FilmCraft](https://github.com/storytold/filmcraft), an open-source non-linear editor, while you watch and correct the timeline in the app.

## Idea

Editing with an AI agent usually means rendering a video, watching it, describing what is wrong, and rendering again. Each round costs time and tokens, and the agent never sees the edits you would rather make yourself.

Here the timeline itself is the shared workspace. Claude drives the running FilmCraft app through its local control port, so every cut appears live in the editor. You can trim, move, or delete clips by hand at any time, then tell Claude "done"; it reads the current timeline and continues from your version. Nothing is exported until you ask.

## Approach

1. **Index the footage locally.** Scene detection (PySceneDetect), speech transcripts with word timings (faster-whisper), and contact sheets run on your machine. Claude reads a compact text index instead of watching the video.
2. **Build the first cut from a cutlist.** Claude matches the script against the index and writes a short JSON cutlist (clip ID, in, out). One command checks it and builds a new sequence in the app.
3. **Edit together.** You change the timeline in FilmCraft; Claude reads a one-line-per-clip summary and makes incremental changes through the same commands the app's menus use. Both of you share one undo history, and Claude's undo refuses to remove a step it did not expect.
4. **Look only when needed.** Claude exports single frames at 640 px when it must check framing or titles.

The design keeps token use low: text summaries replace raw JSON and screenshots, and the heavy analysis runs locally. See [docs/token-cost.md](docs/token-cost.md).

## Platforms

FilmCraft runs on Windows, macOS, and Linux, and the tools here are plain Python with launchers for each shell. Machine-specific paths live in one local config file, written by the setup script. Tested on macOS with FilmCraft 0.20.1; Windows and Linux follow the same code paths but have had less testing.

## Repository layout

| Path | Contents |
|---|---|
| `CLAUDE.md` | Instructions Claude Code loads in this folder: workflow, rules, command reference |
| `bin/` | Launchers: `fc`, `cutlist`, `index-footage`, `start-apps` (Bash) and the same names as `.cmd` (Windows cmd and PowerShell) |
| `tools/` | Python code behind the launchers, plus `bootstrap.py` for setup and `fc_mcp.py` for the optional MCP server |
| `docs/` | [Setup](docs/setup.md), [workflow](docs/workflow.md), [customization](docs/customize.md), [token cost](docs/token-cost.md), and an example cutlist |
| `.claude/settings.json` | Permission rules so Claude Code can run the `bin/` tools without asking each time |
| `requirements.txt` | Packages for footage indexing (the editing tools need only the standard library) |

Created per machine and ignored by Git: `config.local.json`, `.mcp.json`, `.venv/`, and the working folders `footage/`, `script/`, `index/`, `edit/`, `logs/`, `backup/`.

## Quick start

```bash
git clone https://github.com/sigango/Filmcraft_byClaude.git
cd Filmcraft_byClaude
python3 tools/bootstrap.py --lang en      # Windows: py tools\bootstrap.py --lang en
bin/start-apps
claude
```

Install FilmCraft, Python 3.10 or newer, and ffmpeg first; [docs/setup.md](docs/setup.md) covers each platform.

## Roadmap

Effects and titles from EffectCraft (the motion-graphics app from the same family) are planned as a second phase: Claude would build a composition, render it with alpha, and place it on the timeline above the footage.

## License and credits

FilmCraft is developed by the [storytold/filmcraft](https://github.com/storytold/filmcraft) project and is dual-licensed under MIT or Apache-2.0. This repository contains only the agent tooling and does not include FilmCraft. Its license is in [LICENSE](LICENSE).
