# Keeping token cost low

Every Claude Code turn sends the conversation so far, the loaded instructions, and the tool definitions to the model, then adds whatever the commands print. Video editing invites expensive inputs: raw timeline JSON, screenshots, and full-resolution frames. This project replaces each of them with a smaller equivalent and moves the heavy analysis to your machine.

## Measured sizes

Measured with FilmCraft 0.20.1 on a sequence with four video clips, three audio clips, and one marker. Token counts are rough: about 3 to 4 bytes per token for text and JSON, and about width × height / 750 tokens for an image after it is scaled to at most 1568 px on the long edge.

| What Claude reads | Size | Approx. tokens |
|---|---|---|
| `bin/fc seq` (text summary) | 1.0 KB | 300 |
| `bin/fc seq --json` (raw `sequence.inspect`) | 9.1 KB | 3,000 |
| MCP `sequence_inspect` result | 19.5 KB | 6,000 |
| MCP tool definitions (17 tools), sent with every request while the server is on | 11 KB | 3,000 |
| `bin/fc frame` at the default 640 × 360 | image | 300 |
| The same frame at 1920 × 1080 | image | 1,800 |
| A full contact sheet (24 thumbnails, 1920 × 720) | image | 1,200 |
| `CLAUDE.md`, loaded once per session | 6 KB | 1,500 |

## What the tools already do

- **Analysis runs locally.** Scene detection, transcripts with word timings, and contact sheets come from `bin/index-footage` on your CPU or GPU and cost no tokens. Claude reads the resulting text index instead of looking at the video.
- **Text summaries replace raw state.** `bin/fc seq` prints one line per clip. `--no-audio` drops the audio tracks when only the picture matters.
- **Frames are small.** `bin/fc frame` exports at 640 px wide by default; pass `--width 0` only when fine detail matters.
- **One command does many edits.** The first cut is a single `bin/cutlist --apply` built from a short JSON file, and `bin/fc batch` runs a list of commands in one tool call. Fewer tool calls mean fewer round trips that each resend the context.
- **Command lookup is targeted.** `bin/fc find <keyword>` and `bin/fc describe <id>` return a few lines from the 718 FilmCraft commands, so Claude never needs the full reference in context.
- **The MCP server is off by default.** Its tool definitions would ride along with every request; turn it on with `tools/bootstrap.py --mcp` only for UI work such as clicks and drags.

## Habits that help

- **Use one session per video**, and start a new one (or `/clear`) for the next video. Long sessions resend their history every turn; `/compact` shrinks a session that has to continue.
- **Point at things precisely.** Clip IDs (`c61`), timecodes, and timeline markers with comments let Claude act without searching. "Trim the end of c64 by 12 frames" costs less than "the shot after the interview feels long".
- **Read the index selectively.** For hours of footage the transcript section gets long; ask Claude to search it (`grep -n "keyword" index/footage_index.md`) instead of reading it whole.
- **Look at frames only to check something visual**, such as framing, a title, or a color issue. Transcripts and timecodes answer most editing questions.
- **Keep the script in plain text or Markdown** in `script/`. A PDF or a document export is larger and slower to read.
- **Match the model to the task.** Planning a first cut from a long script benefits from the strongest model, while routine trims and moves work well with a faster, cheaper one (`/model` in Claude Code).
- **Do not export to review.** You watch in FilmCraft; Claude exports a video only when you ask for the final file.
- **Keep `CLAUDE.md` short.** It is loaded at the start of every session. Put rarely needed details in `docs/` and let Claude open them when needed.

Claude Code caches the stable part of each request (instructions, tool definitions, earlier turns), and cached input is billed at a reduced rate. Stable files and fewer, larger tool calls make the most of that cache.
