# Editing films in FilmCraft

The user supplies footage and a script. Claude builds the timeline in the running FilmCraft app; the user reviews and edits it directly in the app. Do not export video unless asked. Use one session per video, and reply in the user's language.

## Folders
- `footage/`: source media, read-only. Folders and files whose names start with `_` or `.` are not indexed.
- `script/`: the script. `index/`: `footage_index.md` (read this), `footage_index.json`, `sheets/<ID>.jpg`.
- `edit/main.fcproj`: the project (path set by `project` in `config.local.json`). `backup/<time>/`: the previous project file before each `bin/fc save`. `logs/`: app log and exported frames.
- `bin/`: launchers (`bin/fc` for Bash, `bin\fc.cmd` for cmd or PowerShell). `tools/`: their Python code.

## Starting
- `bin/start-apps` opens FilmCraft with control port 9876 and the project. If the first command answers "still starting", retry after a second or two.
- The control token lives in a private file outside the repository. Never read, print, or copy it; the tools read it themselves.
- `bin/fc ping` checks the app.

## Workflow
1. Index (runs locally, costs no tokens): `bin/index-footage [--lang vi] [--model small|medium|large-v3]`. Read `index/footage_index.md`; open `index/sheets/<ID>.jpg` only when you need to see the shots.
2. First cut: read the script and the index, write `edit/cutlist_v1.json` (format in `docs/cutlist.example.json` and `docs/workflow.md`), check it with `bin/cutlist edit/cutlist_v1.json`, then add `--apply`. Each apply builds a NEW sequence and opens it. Finish with `bin/fc save`.
3. Review loop: the user edits in the app and says "done". First thing each turn: `bin/fc seq` (and `bin/fc history` before any undo). Make incremental changes with `bin/fc run` or `bin/fc batch`, and end the turn with `bin/fc save`.
4. Seeing frames: `bin/fc frame <TC>` writes a 640 px JPEG to `logs/`; read it. Check only a few frames, and do not move the playhead.

## Rules
- Once the user has edited by hand, never rebuild the sequence from a cutlist; change the current sequence.
- Refer to clips by the IDs (`c35`) from this turn's `bin/fc seq`. IDs survive moves, trims, and track changes.
- The user and the agent share one undo stack. Undo only with `bin/fc undo --expect "<step label>"`, never with a bare `edit.undo`.
- Never edit a `.fcproj` file while the app is open; every change goes through the control port.
- Never overwrite media in use: write a new versioned file (`_v002`). The app does not reload files by itself; `media.refreshChanged` notices only a change in size or fingerprint, and `media.replaceFootage` swaps a file completely.
- Prefer text: `bin/fc seq` is about 1 KB, while the MCP `sequence_inspect` is about 20 KB for six clips. Do not capture the whole window (`ui_screenshot`) to see a frame.
- Group operations: `bin/fc batch` (one `{"id","params"}` per line, stops at the first error) or one script in a single Bash call. Each command is still its own undo step.
- `grp 34` in `bin/fc seq` is a link-group ID, not a clip ID.
- Importing OTIO creates a new sequence, duplicates items, and does not link picture to sound; undoing it takes one "Import" step plus one "Link Media" step per file.

## Time
- 254016000000 ticks per second. A cutlist `out` is exclusive; a FilmCraft Out mark is inclusive.
- `timeline.place`, `playhead.set`, `markers.markIn` and `markers.markOut` take the time as a top-level key: `frame`, `seconds`, `timecode`, or `time` (ticks). `"time": {"seconds": 2}` is ignored and the clip lands at 0.
- `timeline.move` is the opposite: `time` holds `{"frame": n}`, `{"seconds": s}`, or `{"timecode": ...}`.
- `markers.add`, `timeline.razor` and `file.exportFrame` take `time` in ticks only.
- `sourceIn` and `duration` of `timeline.place` take ticks or `{"frame": n}`.

## Common commands (`bin/fc run <id> '<json>'` or `key=value` pairs)
| id | main params | notes |
|---|---|---|
| `sequence.inspect` | `{item?}` | use `bin/fc seq` |
| `project.inspect` | | use `bin/fc proj` |
| `file.import` | `{paths:[abs], bin?}` | returns `{items}`; use `bin/fc import` |
| `file.newSequence` | `{name, width, height, fps, video, audio}` | the new sequence becomes active |
| `sequence.open` | `{item}` | |
| `timeline.place` | `{item\|items, track, audioTrack?, frame, insert, sourceIn?, duration?, video?, audio?}` | returns `{clips}`; picture and sound are linked; `track:"new"` adds a track |
| `timeline.move` | `{moves:[{clip, track, time:{frame}}], insert?, linked?}` | linked clips follow |
| `timeline.razor` | `{time:ticks, track?, clip?}` | with `track`, cuts only that track |
| `timeline.delete` | `{clips, ripple?}` | |
| `timeline.trim` | `{clip, edge:in\|out, mode:regular\|ripple, deltaFrames}` | |
| `timeline.slip` | `{clip, deltaFrames}` | |
| `clip.replaceFromBin` | `{clips, item, keepSourceIn}` | keeps clip ID and position |
| `clip.speedDuration` | `{clips, speed, ripple, reverse?}` | |
| `clip.audioGain` | `{clips, mode:set\|adjust, db}` | the audio clip ID (A1), not the link group |
| `trim.applyDefaultTransition` | `{clips}` | 30-frame cross dissolve at both ends |
| `markers.add` | `{target:"program", time:ticks, name, comment?, durationFrames?, color?}` | |
| `markers.markIn` / `markOut` | `{frame\|timecode}` | |
| `playhead.set` | `{frame\|timecode}` | |
| `history.list` | | use `bin/fc history` |
| `media.status` / `media.relink` | `{item?}` / `{item, path}` | file path of an item |
| `file.exportMedia` | `{path, format:h264\|prores, preset?, range:"entire", wait:true}` | only when asked |

Other commands: `bin/fc find <keyword>` lists matching ids, and `bin/fc describe <id>` shows the parameters. Full reference: the FilmCraft docs `agents.md` and `control-protocol.md`.

## MCP
If `.mcp.json` registers `filmcraft` (`python tools/bootstrap.py --mcp`), use it only for `render_frame` or UI actions (`ui_click`, `ui_drag`). Everyday work goes through `bin/fc`, which is far smaller.
