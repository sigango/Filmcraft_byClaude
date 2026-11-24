"""Compact FilmCraft control for the agent (the running app on its control port).

  fc seq [--no-audio] [--json]     the active sequence in a few lines (ids, timecodes, markers)
  fc proj [--json]                 project items: id, type, name, duration
  fc run <id> [json | key=value ...]  run one command, print the result
  fc batch <file.jsonl | ->        run {"id","params"} lines in order, stop at the first error
  fc frame <time> [out] [--width N]  export one Program frame, scaled to N px wide (default 640, 0 = full)
  fc import <path>... [--bin ID]   import media (absolute paths are taken as given)
  fc save                          back up the project file, then save it
  fc ui                            UI state: tool, workspace, playback, open panels
  fc history [n]                   the newest undo / redo step names (user and agent share them)
  fc undo [--expect LABEL] [-n N]  undo, refusing when the newest step is not LABEL
  fc find <keyword>                list command ids matching a keyword (offline, from filmcraft-cli)
  fc describe <id>                 parameters of one command
  fc ping                          is the app listening

time: HH:MM:SS:FF, a frame number or seconds such as 4.5s
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import craft


def parse_params(args):
    if not args:
        return {}
    if len(args) == 1 and args[0].lstrip().startswith("{"):
        return json.loads(args[0])
    out = {}
    for a in args:
        key, _, val = a.partition("=")
        try:
            v = json.loads(val)
        except json.JSONDecodeError:
            v = val
        node = out
        parts = key.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = v
    return out


def compact(obj, limit=4000):
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return s if len(s) <= limit else s[:limit] + f"... ({len(s)} chars)"


def take_option(rest, name, default=None):
    if name in rest:
        i = rest.index(name)
        value = rest[i + 1]
        del rest[i : i + 2]
        return value
    return default


def cli(*args) -> int:
    exe = craft.find_cli()
    if exe is None:
        print("filmcraft-cli not found: set filmcraft_cli in config.local.json", file=sys.stderr)
        return 1
    return subprocess.call([str(exe), *args])


def export_frame(fc, rest) -> int:
    width = int(take_option(rest, "--width", 640))
    if not rest:
        print("usage: fc frame <time> [out.png|out.jpg] [--width N]", file=sys.stderr)
        return 2
    seq = fc.run("sequence.inspect")
    num, den = craft.rate_of(seq)
    frame = craft.parse_time(rest[0], craft.nominal_fps(num, den))
    out = Path(rest[1]).resolve() if len(rest) > 1 else craft.ROOT / "logs" / f"frame_{frame}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    scale = width > 0 and ffmpeg is not None
    with tempfile.TemporaryDirectory() as tmp:
        full = Path(tmp) / "full.png" if scale else out
        fmt = "jpeg" if full.suffix.lower() in (".jpg", ".jpeg") else "png"
        fc.run("file.exportFrame", {"path": str(full), "format": fmt, "target": "program",
                                    "time": craft.frame_to_ticks(frame, num, den)})
        if scale:
            subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(full), "-vf", f"scale='min({width},iw)':-2",
                            "-q:v", "3", str(out)], check=True)
    note = "" if scale or width == 0 else " (full size: ffmpeg not found)"
    print(f"frame {frame} -> {out}{note}")
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "find":
        return cli("commands", *rest)
    if cmd == "describe":
        return cli("describe", *rest)
    fc = craft.filmcraft()

    if cmd == "ping":
        print("FilmCraft up" if fc.alive() else "FilmCraft not listening")
        return 0
    if cmd == "seq":
        seq = fc.run("sequence.inspect")
        if "--json" in rest:
            print(json.dumps(seq, ensure_ascii=False))
        else:
            print(craft.summarize_sequence(seq, show_audio="--no-audio" not in rest))
        return 0
    if cmd == "proj":
        proj = fc.run("project.inspect")
        if "--json" in rest:
            print(json.dumps(proj, ensure_ascii=False))
            return 0
        print(f"PROJECT {proj.get('name')} path={proj.get('path')} dirty={proj.get('dirty')} active seq={proj.get('activeSequence')}")

        def walk(node, depth):
            for ch in node.get("children", []) or []:
                ident = ch.get("item", ch.get("id"))
                dur = ch.get("duration")
                dur_s = f" {dur / craft.TICKS:.2f}s" if dur else ""
                print(f"{'  ' * depth}{ident} {ch.get('type', 'Bin')} {ch.get('name')!r}{dur_s}")
                walk(ch, depth + 1)

        walk(proj.get("root", {}), 0)
        return 0
    if cmd == "run":
        if not rest:
            print("usage: fc run <command-id> [json | key=value ...]", file=sys.stderr)
            return 2
        print(compact(fc.run(rest[0], parse_params(rest[1:]))))
        return 0
    if cmd == "batch":
        src = sys.stdin if not rest or rest[0] == "-" else open(rest[0], encoding="utf-8")
        for n, line in enumerate(src, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            step = json.loads(line)
            try:
                res = fc.run(step["id"], step.get("params", {}))
                print(f"{n} ok {step['id']} {compact(res, 600)}")
            except craft.ControlError as exc:
                print(f"{n} FAIL {step['id']} {exc}")
                return 1
        return 0
    if cmd == "frame":
        return export_frame(fc, rest)
    if cmd == "import":
        bin_id = take_option(rest, "--bin")
        params = {"paths": [str(Path(p).resolve()) for p in rest]}
        if bin_id is not None:
            params["bin"] = int(bin_id)
        print(compact(fc.run("file.import", params)))
        return 0
    if cmd == "save":
        proj = fc.run("project.inspect")
        path = Path(proj.get("path") or craft.EDIT_PROJECT)
        bk = craft.backup_file(path)
        res = fc.run("file.save", {"path": str(path)} if not proj.get("path") else {})
        print(f"saved {path}" + (f" (previous copy in {bk})" if bk else "") + f" {compact(res, 300)}")
        return 0
    if cmd == "ui":
        print(compact(fc.call("ui.inspect"), 3000))
        return 0
    if cmd == "history":
        n = int(rest[0]) if rest else 8
        h = fc.run("history.list")
        print("undo (newest last): " + " | ".join(h.get("undo", [])[-n:]))
        if h.get("redo"):
            print("redo: " + " | ".join(h["redo"][-n:]))
        return 0
    if cmd == "undo":
        expect = take_option(rest, "--expect")
        steps = int(take_option(rest, "-n", 1))
        for _ in range(steps):
            top = (fc.run("history.list").get("undo") or [None])[-1]
            if expect is not None and top != expect:
                print(f"refused: the newest step is {top!r}, not {expect!r} (someone else edited since?)", file=sys.stderr)
                return 1
            print(compact(fc.run("edit.undo")))
        return 0
    print(f"unknown subcommand {cmd!r}\n\n{__doc__.strip()}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except craft.ControlError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
