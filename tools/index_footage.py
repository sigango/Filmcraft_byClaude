"""Index the footage folder on this machine: probe, scenes, transcript, contact sheet.

  bin/index-footage [DIR] [--lang vi] [--model small] [--device auto] [--no-whisper] [--threshold 27] [--force]

DIR defaults to footage/ (or "footage_dir" in config.local.json) and may be outside the repository.

Writes index/footage_index.md (for reading), index/footage_index.json (for scripts) and
index/sheets/<ID>.jpg. Each file gets a short stable ID (A001, A002, ...) kept in index/ids.json.
Results are cached per file (path, size, mtime) in index/cache/, so a rerun only does new files.
Folders and files whose names start with "_" or "." are skipped (footage/_test holds test clips).
Timecodes are media time from the first frame of the file, on the file's own frame rate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import craft

ROOT = craft.ROOT
INDEX = ROOT / "index"
CACHE = INDEX / "cache"
SHEETS = INDEX / "sheets"
IDS = INDEX / "ids.json"
VIDEO_EXT = {".mp4", ".mov", ".mxf", ".mkv", ".avi", ".m4v", ".mts", ".m2ts", ".webm", ".braw", ".r3d"}
AUDIO_EXT = {".wav", ".aif", ".aiff", ".mp3", ".m4a", ".flac", ".aac"}
SHEET_MAX = 24


def tc(frame: int, fps: int) -> str:
    s, ff = divmod(max(frame, 0), fps)
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{ff:02d}"


def secs_tc(seconds: float, fps: int) -> str:
    return tc(round(seconds * fps), fps)


def ratio(text: str | None) -> float:
    if not text or text in ("0/0", "N/A"):
        return 0.0
    if "/" in text:
        a, b = text.split("/")
        return float(a) / float(b) if float(b) else 0.0
    return float(text)


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    fmt = data.get("format", {})
    v = next((s for s in data["streams"] if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic")), None)
    a = [s for s in data["streams"] if s["codec_type"] == "audio"]
    info = {"duration": float(fmt.get("duration") or 0), "container": fmt.get("format_name"), "size": int(fmt.get("size") or 0)}
    tags = {**fmt.get("tags", {}), **(v or {}).get("tags", {})}
    info["timecode"] = tags.get("timecode")
    info["created"] = tags.get("creation_time")
    if v:
        r, avg = ratio(v.get("r_frame_rate")), ratio(v.get("avg_frame_rate"))
        info["video"] = {
            "codec": v.get("codec_name"), "profile": v.get("profile"), "width": v.get("width"), "height": v.get("height"),
            "fps": round(avg or r, 3), "rate": v.get("avg_frame_rate") or v.get("r_frame_rate"),
            "vfr": bool(r and avg and abs(r - avg) > 0.01), "pix_fmt": v.get("pix_fmt"),
            "rotation": next((sd.get("rotation") for sd in v.get("side_data_list", []) if "rotation" in sd), None),
            "frames": int(v["nb_frames"]) if v.get("nb_frames", "N/A") != "N/A" else None,
        }
    info["audio"] = [
        {"codec": s.get("codec_name"), "rate": int(s.get("sample_rate") or 0), "channels": s.get("channels")} for s in a
    ]
    return info


# Each worker runs in its own process: OpenCV and PyAV must not load in one process on macOS.


def worker_scenes(path: str, threshold: float, sheet: str, fps: int) -> None:
    import cv2
    from scenedetect import ContentDetector, detect

    scenes = detect(path, ContentDetector(threshold=threshold), show_progress=False)
    cuts = [(s.get_frames(), e.get_frames()) for s, e in scenes]
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    if not cuts and total:
        cuts = [(0, total)]
    picks = [(a + b) // 2 for a, b in cuts]
    if len(picks) > SHEET_MAX:
        step = len(picks) / SHEET_MAX
        picks = [picks[int(i * step)] for i in range(SHEET_MAX)]
    if not picks and total:
        picks = [total * i // 8 for i in range(8)]
    thumbs = []
    for f in picks:
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ok, img = cap.read()
        if not ok:
            continue
        h, w = img.shape[:2]
        tw = 320
        img = cv2.resize(img, (tw, max(1, round(h * tw / w))))
        label = tc(f, fps)
        cv2.rectangle(img, (0, img.shape[0] - 24), (tw, img.shape[0]), (0, 0, 0), -1)
        cv2.putText(img, label, (6, img.shape[0] - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        thumbs.append(img)
    if thumbs:
        import numpy as np

        cols = min(6, len(thumbs))
        th = max(t.shape[0] for t in thumbs)
        rows = []
        for i in range(0, len(thumbs), cols):
            row = [cv2.copyMakeBorder(t, 0, th - t.shape[0], 0, 0, cv2.BORDER_CONSTANT) for t in thumbs[i : i + cols]]
            row += [np.zeros_like(row[0])] * (cols - len(row))
            rows.append(np.hstack(row))
        cv2.imwrite(sheet, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 80])
    print(json.dumps({"scenes": cuts, "sheet": sheet if thumbs else None}))


def worker_whisper(paths: list[str], model: str, lang: str | None, device: str) -> None:
    import numpy as np
    from faster_whisper import WhisperModel

    if device == "auto":
        import ctranslate2

        device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    wm = WhisperModel(model, device=device, compute_type="float16" if device == "cuda" else "int8")
    for p in paths:
        pcm = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", p, "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
            capture_output=True, check=True,
        ).stdout
        audio = np.frombuffer(pcm, dtype=np.float32)
        segments, info = wm.transcribe(audio, language=lang, vad_filter=True, beam_size=5, word_timestamps=True)
        segs = [
            {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
             "words": [[round(w.start, 2), round(w.end, 2), w.word.strip()] for w in (s.words or [])]}
            for s in segments
        ]
        print(json.dumps({"path": p, "language": info.language, "segments": segs}, ensure_ascii=False), flush=True)


def cache_key(path: Path) -> str:
    st = path.stat()
    raw = f"{path.resolve()}|{st.st_size}|{int(st.st_mtime)}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def rel(path: Path) -> str:
    """Repository-relative path with forward slashes, or the absolute path for media kept elsewhere."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def assign_ids(files: list[Path]) -> dict:
    ids = json.loads(IDS.read_text(encoding="utf-8")) if IDS.exists() else {}
    used = set(ids.values())
    n = max([int(v[1:]) for v in used if v[1:].isdigit()] or [0])
    for f in files:
        key = rel(f)
        if key not in ids:
            n += 1
            ids[key] = f"A{n:03d}"
    IDS.write_text(json.dumps(ids, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return ids


def run_worker(args: list[str]) -> str:
    env = {**os.environ, "PYTHONUTF8": "1"}
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", *args],
                          capture_output=True, text=True, encoding="utf-8", env=env)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[-2000:])
    return proc.stdout


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        kind, rest = sys.argv[2], sys.argv[3:]
        if kind == "scenes":
            worker_scenes(rest[0], float(rest[1]), rest[2], int(rest[3]))
        else:
            worker_whisper(rest[3:], rest[0], rest[1] or None, rest[2])
        return 0

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    whisper = craft.CONFIG.get("whisper", {})
    ap.add_argument("dir", nargs="?", default=craft.CONFIG.get("footage_dir", "footage"))
    ap.add_argument("--lang", default=whisper.get("lang", "auto"), help="spoken language (vi, en, ...; 'auto' to detect)")
    ap.add_argument("--model", default=whisper.get("model", "small"), help="faster-whisper model: small, medium, large-v3, ...")
    ap.add_argument("--device", default=whisper.get("device", "auto"), choices=["auto", "cpu", "cuda"],
                    help="cuda needs an NVIDIA GPU (Windows, Linux); auto picks it when present")
    ap.add_argument("--no-whisper", action="store_true")
    ap.add_argument("--threshold", type=float, default=27.0, help="PySceneDetect content threshold")
    ap.add_argument("--force", action="store_true", help="ignore the cache")
    args = ap.parse_args()

    base = craft.project_path(args.dir).resolve()
    files = sorted(
        p for p in base.rglob("*")
        if p.suffix.lower() in VIDEO_EXT | AUDIO_EXT
        and not any(part.startswith((".", "_")) for part in p.relative_to(base).parts)
    )
    if not files:
        print(f"no media under {base}")
        return 1
    for d in (CACHE, SHEETS):
        d.mkdir(parents=True, exist_ok=True)
    ids = assign_ids(files)

    records, todo_whisper = [], []
    for f in files:
        path = rel(f)
        cid = ids[path]
        cfile = CACHE / f"{cache_key(f)}.json"
        rec = json.loads(cfile.read_text(encoding="utf-8")) if cfile.exists() and not args.force else {}
        rec.update(id=cid, path=path, cache=rel(cfile))
        if "probe" not in rec:
            rec["probe"] = probe(f)
        v = rec["probe"].get("video")
        fps = round(v["fps"]) if v and v.get("fps") else 25
        rec["fps"] = fps
        if v and "scenes" not in rec:
            print(f"{cid} scenes {path}", file=sys.stderr)
            sheet = SHEETS / f"{cid}.jpg"
            rec.update(json.loads(run_worker(["scenes", str(f), str(args.threshold), str(sheet), str(fps)])))
            if rec.get("sheet"):
                rec["sheet"] = rel(Path(rec["sheet"]))
        if rec["probe"]["audio"] and "transcript" not in rec and not args.no_whisper:
            todo_whisper.append((f, rec))
        cfile.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        records.append(rec)

    if todo_whisper:
        lang = "" if args.lang == "auto" else args.lang
        print(f"whisper {args.model} on {len(todo_whisper)} file(s)", file=sys.stderr)
        out = run_worker(["whisper", args.model, lang, args.device, *[str(f) for f, _ in todo_whisper]])
        by_path = {json.loads(line)["path"]: json.loads(line) for line in out.splitlines() if line.strip()}
        for f, rec in todo_whisper:
            res = by_path.get(str(f))
            if res:
                rec["transcript"] = {"model": args.model, "language": res["language"], "segments": res["segments"]}
                (ROOT / rec["cache"]).write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")

    write_outputs(records, args)
    return 0


def write_outputs(records: list[dict], args) -> None:
    (INDEX / "footage_index.json").write_text(json.dumps(records, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    total = sum(r["probe"]["duration"] for r in records)
    lines = [
        "# Footage index",
        f"{datetime.now():%Y-%m-%d %H:%M} · {len(records)} file(s) · {total / 60:.1f} min · "
        f"scenes threshold {args.threshold} · " + ("no transcript" if args.no_whisper else f"whisper {args.model} ({args.lang})"),
        "Timecodes are media time from each file's first frame. Use the ID in cutlists.",
        "",
    ]
    for r in records:
        p, fps = r["probe"], r["fps"]
        v = p.get("video")
        head = f"## {r['id']} {r['path']}"
        spec = []
        if v:
            spec.append(f"{v['width']}x{v['height']} {v['fps']:g}fps {v['codec']}")
            if v.get("vfr"):
                spec.append("VFR!")
            if v.get("rotation"):
                spec.append(f"rot {v['rotation']}")
        spec.append(f"dur {secs_tc(p['duration'], fps)}")
        if p["audio"]:
            a = p["audio"][0]
            spec.append(f"audio {a['codec']} {a['rate'] // 1000}k {a['channels']}ch" + (f" x{len(p['audio'])}" if len(p["audio"]) > 1 else ""))
        else:
            spec.append("no audio")
        if p.get("timecode"):
            spec.append(f"cam TC {p['timecode']}")
        if r.get("sheet"):
            spec.append(f"sheet {r['sheet']}")
        lines += [head, " · ".join(spec)]
        if r.get("scenes"):
            sc = r["scenes"]
            lines.append("Scenes: " + "  ".join(f"{i}) {tc(a, fps)}-{tc(b, fps)}" for i, (a, b) in enumerate(sc, 1)))
        tr = r.get("transcript")
        if tr and tr["segments"]:
            lines.append(f"Transcript ({tr['language']}):")
            lines += [f"[{secs_tc(s['start'], fps)}-{secs_tc(s['end'], fps)}] {s['text']}" for s in tr["segments"]]
        elif tr:
            lines.append("Transcript: (no speech)")
        lines.append("")
    (INDEX / "footage_index.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote index/footage_index.md ({len(records)} files)")


if __name__ == "__main__":
    sys.exit(main())
