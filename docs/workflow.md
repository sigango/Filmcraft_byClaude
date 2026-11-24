# Editing workflow

This page describes one editing session from the user's side, and the cutlist format Claude writes for the first cut.

## The loop

1. **Start.** Run `bin/start-apps`, then `claude` in the repository folder. Use one Claude Code session per video.
2. **Index.** After adding footage, run `bin/index-footage` (or ask Claude to run it). Each file gets a stable ID such as `A001`; the IDs stay the same when you add more footage later.
3. **First cut.** Ask Claude to build a cut from the script. It writes `edit/cutlist_v1.json`, checks it with `bin/cutlist`, builds a new sequence with `--apply`, and saves the project.
4. **Your edits.** Watch and change the timeline in FilmCraft as you normally would: trim, move, delete, add transitions.
5. **Hand back.** Tell Claude what you want next and say "done". Claude reads the current timeline with `bin/fc seq` before changing anything, so it builds on your edits and does not rebuild the sequence.
6. **Repeat** steps 4 and 5. Claude saves the project at the end of each turn; the previous file is copied to `backup/` first.

Claude and you share one undo history. Claude only undoes a step when the newest step has the name it expects, so it cannot undo your work by accident. Export happens only when you ask for it.

## What Claude sees

`bin/fc seq` prints the active sequence in a few lines:

```
SEQ Rough cut v1 (id 59) 1920x1080 25/1fps dur 00:00:07:15
V1 Video 1: 3 clip(s)
  c61 item9 'interview_A.mp4' rec 00:00:00:00-00:00:03:00 (75f) src 00:00:00:00-00:00:03:00 grp 60
  c64 item10 'broll_B.mp4' rec 00:00:03:00-00:00:05:00 (50f) src 00:00:01:00-00:00:03:00 grp 63
  ...
M70 00:00:01:00 +50f Green 'title' — lower third goes here
```

`c61` is a clip ID, `rec` is the position on the timeline, `src` is the range taken from the media, and `grp` is the link group that ties picture to sound. When you talk to Claude, timecodes and clip IDs from this view are the most precise references. Markers with comments are another good way to leave notes for Claude on the timeline.

## Cutlist format

```json
{"name": "Rough cut v1",
 "settings": {"width": 1920, "height": 1080, "fps": 25},
 "events": [
   {"src": "A002", "in": "00:00:00:00", "out": "00:00:03:00", "note": "greeting"},
   {"src": "A003", "in": "1s", "out": "3s"},
   {"src": "A001", "in": "6s", "out": "7s", "at": "00:00:01:00", "track": "V2", "note": "cutaway"}],
 "markers": [{"at": "00:00:01:00", "name": "title", "dur": 50, "comment": "lower third goes here"}]}
```

- `src` is the clip ID from `index/footage_index.md`. `in` and `out` are media time in that file (timecode, frames, or seconds such as `4.5s`), and `out` is exclusive.
- Events without `at` are placed one after another on V1 with their sound on A1, linked.
- An event with `at` goes to that sequence time on `track` (default V2) without sound, unless it has `"audio": true`.
- `settings` is optional; by default the sequence takes the size and frame rate of the first clip.
- `bin/cutlist file.json` only checks the cutlist and prints the plan. `--apply` builds a new sequence (adding a number to the name if it exists), and `--otio out.otio` also writes an OpenTimelineIO file of the same cut.
