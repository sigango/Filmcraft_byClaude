"""Build a FilmCraft sequence from a compact cutlist (clip IDs from index/footage_index.md).

  cutlist <cutlist.json>                 check it and print the plan (nothing changes)
  cutlist <cutlist.json> --apply         build it as a NEW sequence in the running app and open it
  cutlist <cutlist.json> --otio OUT.otio also write an OpenTimelineIO file of the same cut

cutlist.json:
  {"name": "Main v1",                          # sequence name (a number is added if it exists)
   "settings": {"width": 1920, "height": 1080, "fps": 25},   # optional; default: the first clip
   "events": [
     {"src": "A001", "in": "00:00:01:00", "out": "00:00:04:00", "note": "intro"},
     {"src": "A002", "in": "2s", "out": "4.5s"},
     {"src": "A001", "in": "6s", "out": "7s", "track": "V2", "at": "00:00:02:00"}],
   "markers": [{"at": "00:00:03:00", "name": "fx:title01", "dur": 50, "comment": "..."}]}

Events without "at" go one after another on V1 with their sound on A1, linked. An event with "at"
(sequence time) goes exactly there, on "track" (default V2), without sound unless "audio": true.
"in"/"out" are media time of the source (TC, frames or seconds on its own rate); out is exclusive.
"""

from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

import craft

ROOT = craft.ROOT
INDEX_JSON = ROOT / "index" / "footage_index.json"


def media_rate(rec) -> Fraction:
    v = rec["probe"].get("video") or {}
    rate = v.get("rate")
    if rate and "/" in rate and not rate.startswith("0/"):
        a, b = rate.split("/")
        return Fraction(int(a), int(b))
    return Fraction(rec.get("fps") or 25)


def parse_media_time(value, rate: Fraction) -> Fraction:
    """Media time in seconds as a Fraction."""
    fps = round(rate)
    v = str(value).strip()
    if v.endswith("s") and v[:-1].replace(".", "", 1).isdigit():
        return Fraction(v[:-1])
    return Fraction(craft.parse_time(v, fps)) / rate


def plan(cut: dict, index: dict):
    events = cut.get("events", [])
    if not events:
        raise SystemExit("error: no events")
    first = index.get(events[0]["src"])
    if first is None:
        raise SystemExit(f"error: unknown clip {events[0]['src']!r}")
    st = dict(cut.get("settings") or {})
    v0 = first["probe"].get("video") or {}
    st.setdefault("width", v0.get("width", 1920))
    st.setdefault("height", v0.get("height", 1080))
    st.setdefault("fps", float(media_rate(first)) if v0 else 25)
    seq_rate = Fraction(st["fps"]).limit_denominator(1001)
    sfps = round(seq_rate)

    rows, cursor, problems = [], 0, []
    for i, ev in enumerate(events, start=1):
        rec = index.get(ev["src"])
        if rec is None:
            problems.append(f"event {i}: unknown clip {ev['src']!r}")
            continue
        rate = media_rate(rec)
        t_in, t_out = parse_media_time(ev["in"], rate), parse_media_time(ev["out"], rate)
        dur_media = Fraction(str(rec["probe"]["duration"]))
        if t_out <= t_in:
            problems.append(f"event {i}: out before in")
        if t_in < 0 or t_out > dur_media + Fraction(1, 1000):
            problems.append(f"event {i}: {ev['src']} is {float(dur_media):.2f}s long; range {float(t_in):.2f}-{float(t_out):.2f}s")
        rec_frames = round((t_out - t_in) * seq_rate)
        if "at" in ev:
            start = craft.parse_time(ev["at"], sfps)
            track = ev.get("track", "V2")
            audio = bool(ev.get("audio", False))
        else:
            start = cursor
            cursor += rec_frames
            track = ev.get("track", "V1")
            audio = bool(ev.get("audio", True)) and bool(rec["probe"]["audio"])
        rows.append({"i": i, "ev": ev, "rec": rec, "t_in": t_in, "start": start, "frames": rec_frames,
                     "track": track, "audio": audio and bool(rec["probe"]["audio"])})
    for p in problems:
        print("PROBLEM " + p)
    return st, seq_rate, rows, bool(problems)


def print_plan(name, st, seq_rate, rows):
    sfps = round(seq_rate)
    end = max((r["start"] + r["frames"] for r in rows), default=0)
    print(f"{name}: {st['width']}x{st['height']} {float(seq_rate):g}fps, {len(rows)} events, {craft.frame_to_tc(end, sfps)}")
    for r in rows:
        mfps = round(media_rate(r["rec"]))
        src_in = round(r["t_in"] * media_rate(r["rec"]))
        print(f"  {r['i']:>2} {r['track']}{'+A' if r['audio'] else ''} {craft.frame_to_tc(r['start'], sfps)}"
              f"-{craft.frame_to_tc(r['start'] + r['frames'], sfps)} {r['ev']['src']} "
              f"{craft.frame_to_tc(src_in, mfps)} ({r['frames']}f)" + (f"  {r['ev']['note']}" if r["ev"].get("note") else ""))


def apply(cut, st, seq_rate, rows):
    fc = craft.filmcraft()
    status = fc.run("media.status")
    by_path = {}
    for s in status or []:
        by_path.setdefault(craft.same_path(s["path"]), s["item"])
    files = {craft.same_path(ROOT / r["rec"]["path"]): str((ROOT / r["rec"]["path"]).resolve()) for r in rows}
    need = sorted(set(files) - set(by_path))
    if need:
        proj = fc.run("project.inspect")
        bin_id = next((c["id"] for c in proj["root"].get("children", []) if "item" not in c and c.get("name") == "Footage"), None)
        if bin_id is None:
            bin_id = fc.run("file.newBin", {"name": "Footage"})["bin"]
        res = fc.run("file.import", {"paths": [files[k] for k in need], "bin": bin_id})
        if res.get("errors"):
            raise SystemExit(f"error: import failed: {res['errors']}")
        for p, item in zip(need, res["items"]):
            by_path[p] = item

    existing = {c.get("name") for c in craft.item_index(fc.run("project.inspect")).values()}
    name, n = cut.get("name", "Cut"), 2
    base = name
    while name in existing:
        name, n = f"{base} {n}", n + 1
    num, den = seq_rate.numerator, seq_rate.denominator
    seq_id = fc.run("file.newSequence", {"name": name, "width": st["width"], "height": st["height"],
                                         "fps": float(seq_rate), "video": max(3, *(int(r["track"][1:]) for r in rows)),
                                         "audio": 2})["sequence"]
    for r in rows:
        item = by_path[craft.same_path(ROOT / r["rec"]["path"])]
        params = {
            "item": item, "track": r["track"], "time": craft.frame_to_ticks(r["start"], num, den), "insert": False,
            "sourceIn": int(r["t_in"] * craft.TICKS), "duration": craft.frame_to_ticks(r["frames"], num, den),
            "video": True, "audio": r["audio"],
        }
        if r["audio"]:
            params["audioTrack"] = r["ev"].get("audioTrack", "A1")
        fc.run("timeline.place", params)
    for mk in cut.get("markers", []):
        p = {"target": "program", "time": craft.frame_to_ticks(craft.parse_time(mk["at"], round(seq_rate)), num, den),
             "name": mk.get("name", "")}
        if mk.get("comment"):
            p["comment"] = mk["comment"]
        if mk.get("dur"):
            p["durationFrames"] = int(mk["dur"])
        fc.run("markers.add", p)
    print(f"built sequence {name!r} (id {seq_id}); it is now the active sequence")
    print(craft.summarize_sequence(fc.run("sequence.inspect"), show_audio=False))


def write_otio(path: Path, name, seq_rate, rows):
    rate = float(seq_rate)

    def rt(v):
        return {"OTIO_SCHEMA": "RationalTime.1", "rate": rate, "value": float(v)}

    def tr(s, d):
        return {"OTIO_SCHEMA": "TimeRange.1", "start_time": rt(s), "duration": rt(d)}

    def base(schema, nm, rng):
        return {"OTIO_SCHEMA": schema, "name": nm, "source_range": rng, "effects": [], "markers": [], "enabled": True, "metadata": {}}

    tracks = {}
    for r in sorted(rows, key=lambda r: r["start"]):
        for kind, tname in (("Video", r["track"]), ("Audio", "A1" if r["audio"] else None)):
            if not tname:
                continue
            t = tracks.setdefault(tname, {"kind": kind, "children": [], "end": 0})
            if r["start"] > t["end"]:
                t["children"].append(base("Gap.1", "", tr(0, r["start"] - t["end"])))
            clip = base("Clip.2", r["ev"]["src"], tr(float(r["t_in"] * seq_rate), r["frames"]))
            clip["media_references"] = {"DEFAULT_MEDIA": {"OTIO_SCHEMA": "ExternalReference.1", "name": r["ev"]["src"],
                                                          "target_url": (ROOT / r["rec"]["path"]).resolve().as_uri(),
                                                          "available_range": None, "metadata": {}}}
            clip["active_media_reference_key"] = "DEFAULT_MEDIA"
            t["children"].append(clip)
            t["end"] = r["start"] + r["frames"]
    order = sorted(tracks, key=lambda k: (k[0] != "V", int(k[1:])))
    stack = base("Stack.1", "tracks", None)
    stack["children"] = [{**base("Track.1", k, None), "kind": tracks[k]["kind"], "children": tracks[k]["children"]} for k in order]
    tl = {"OTIO_SCHEMA": "Timeline.1", "name": name, "global_start_time": rt(0), "metadata": {}, "tracks": stack}
    path.write_text(json.dumps(tl, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cutlist")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--otio")
    args = ap.parse_args()
    cut = json.loads(Path(args.cutlist).read_text(encoding="utf-8"))
    if not INDEX_JSON.exists():
        raise SystemExit("error: run bin/index-footage first")
    index = {r["id"]: r for r in json.loads(INDEX_JSON.read_text(encoding="utf-8"))}
    st, seq_rate, rows, bad = plan(cut, index)
    print_plan(cut.get("name", "Cut"), st, seq_rate, rows)
    if bad:
        raise SystemExit(1)
    if args.otio:
        write_otio(Path(args.otio), cut.get("name", "Cut"), seq_rate, rows)
    if args.apply:
        apply(cut, st, seq_rate, rows)


if __name__ == "__main__":
    try:
        main()
    except craft.ControlError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
