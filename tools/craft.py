"""Shared helpers for driving the FilmCraft desktop app over its control port.

The app speaks one JSON object per line over TCP on 127.0.0.1, and every request carries
FILMCRAFT_CONTROL_TOKEN. Machine-specific paths live in config.local.json (written by
tools/bootstrap.py); environment variables override it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config.local.json"
BACKUP = ROOT / "backup"
TICKS = 254_016_000_000  # FilmCraft time unit: ticks per second
WINDOWS = os.name == "nt"


class ControlError(RuntimeError):
    pass


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


CONFIG = load_json(CONFIG_FILE, {})


def setting(key: str, env: str | None = None, default=None):
    if env and os.environ.get(env):
        return os.environ[env]
    return CONFIG.get(key, default)


def project_path(value: str | os.PathLike) -> Path:
    """Paths in the config may be relative to the repository root."""
    p = Path(os.path.expandvars(os.path.expanduser(str(value))))
    return p if p.is_absolute() else ROOT / p


def default_token_file() -> Path:
    if WINDOWS:
        return Path(os.environ.get("APPDATA", Path.home())) / "filmcraft-agent" / "token"
    return Path.home() / ".config" / "filmcraft-agent" / "token"


FC_PORT = int(setting("control_port", "FILMCRAFT_CONTROL_PORT", 9876))
TOKEN_FILE = project_path(setting("token_file", "FILMCRAFT_TOKEN_FILE", default_token_file()))
EDIT_PROJECT = project_path(setting("project", "FILMCRAFT_PROJECT", "edit/main.fcproj"))


def _install_dirs() -> list[Path]:
    if WINDOWS:
        env = os.environ
        dirs = [ROOT / "vendor" / "filmcraft"]
        if env.get("LOCALAPPDATA"):
            dirs.append(Path(env["LOCALAPPDATA"], "Programs", "ArtCraft", "FilmCraft"))
        for var in ("ProgramFiles", "ProgramFiles(x86)"):
            if env.get(var):
                dirs.append(Path(env[var], "ArtCraft", "FilmCraft"))
        return dirs
    if sys.platform == "darwin":
        return [ROOT / "vendor" / "bin", Path("/usr/local/bin"), Path("/opt/homebrew/bin"), Path.home() / ".local" / "bin"]
    return [ROOT / "vendor" / "bin", Path.home() / ".local" / "bin", Path("/usr/local/bin"), Path("/usr/bin")]


def _first(paths) -> Path | None:
    for p in paths:
        if p and Path(p).is_file():
            return Path(p)
    return None


def _on_path(name: str) -> Path | None:
    found = shutil.which(name)
    return Path(found) if found else None


def find_app() -> Path | None:
    """The FilmCraft desktop executable: config, then the usual install places."""
    configured = setting("filmcraft_app", "FILMCRAFT_APP")
    if configured:
        return project_path(configured)
    if sys.platform == "darwin":
        bundles = [ROOT / "vendor" / "apps", Path("/Applications"), Path.home() / "Applications"]
        return _first(b / "FilmCraft.app" / "Contents" / "MacOS" / "FilmCraft" for b in bundles)
    name = "filmcraft.exe" if WINDOWS else "filmcraft"
    return _first(d / name for d in _install_dirs()) or _on_path("filmcraft")


def find_cli() -> Path | None:
    """filmcraft-cli: config, then the usual install places, then PATH."""
    configured = setting("filmcraft_cli", "FILMCRAFT_CLI")
    if configured:
        return project_path(configured)
    name = "filmcraft-cli.exe" if WINDOWS else "filmcraft-cli"
    return _first(d / name for d in _install_dirs()) or _on_path("filmcraft-cli")


def fc_token() -> str | None:
    token = os.environ.get("FILMCRAFT_CONTROL_TOKEN")
    if token:
        return token.strip()
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    return None


class Control:
    """One persistent connection to the app's control channel."""

    def __init__(self, port: int, token: str, name: str = "FilmCraft"):
        self.port = port
        self.token = token
        self.name = name
        self._sock = None
        self._file = None
        self._id = 0

    def _connect(self):
        if self._sock is None:
            try:
                self._sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
            except OSError as exc:
                raise ControlError(
                    f"{self.name} is not listening on 127.0.0.1:{self.port} (start it with bin/start-apps): {exc}"
                ) from exc
            self._sock.settimeout(None)
            self._file = self._sock.makefile("rwb")

    def close(self):
        if self._sock is not None:
            self._sock.close()
        self._sock = self._file = None

    def alive(self) -> bool:
        try:
            self._connect()
            return True
        except ControlError:
            return False

    def call(self, method: str, params: dict | None = None):
        self._connect()
        self._id += 1
        req = {"id": self._id, "token": self.token, "method": method, "params": params or {}}
        self._file.write((json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"))
        self._file.flush()
        line = self._file.readline()
        if not line:
            self.close()
            raise ControlError(f"{self.name} closed the connection")
        reply = json.loads(line)
        if not reply.get("ok"):
            err = reply.get("error", "unknown error")
            if "closing the connection" in str(err):
                self.close()
            raise ControlError(f"{method}: {err}")
        return reply.get("result")

    def run(self, command: str, params: dict | None = None):
        return self.call("engine.execute", {"command": command, "params": params or {}})


def filmcraft() -> Control:
    token = fc_token()
    if not token:
        raise ControlError(f"no FilmCraft token: run bin/start-apps (token file {TOKEN_FILE})")
    return Control(FC_PORT, token)


def port_open(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
        return True
    except OSError:
        return False


def wait_port(port: int, seconds: float = 30) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if port_open(port):
            return True
        time.sleep(0.5)
    return False


def rate_of(seq: dict) -> tuple[int, int]:
    fr = seq["settings"]["frame_rate"]
    return fr["num"], fr["den"]


def nominal_fps(num: int, den: int) -> int:
    return round(num / den)


def ticks_to_frame(ticks: int, num: int, den: int) -> int:
    return round(ticks * num / (den * TICKS))


def frame_to_ticks(frame: int, num: int, den: int) -> int:
    return frame * den * TICKS // num


def frame_to_tc(frame: int, fps: int) -> str:
    sign = "-" if frame < 0 else ""
    frame = abs(frame)
    ff = frame % fps
    s = frame // fps
    return f"{sign}{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{ff:02d}"


def parse_time(value: str | int, fps: int) -> int:
    """'HH:MM:SS:FF', '123' / 123 (frames) or '4.5s' (seconds) -> frames."""
    if isinstance(value, int):
        return value
    v = str(value).strip()
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if v.endswith("s") and re.fullmatch(r"-?\d+(\.\d+)?s", v):
        return round(float(v[:-1]) * fps)
    m = re.fullmatch(r"(\d+):(\d\d):(\d\d)[:;](\d\d)", v)
    if not m:
        raise ValueError(f"bad time {value!r}: use HH:MM:SS:FF, frames or 4.5s")
    h, mi, s, f = map(int, m.groups())
    return ((h * 60 + mi) * 60 + s) * fps + f


def clips_of(seq: dict):
    """Yield (kind, track_name, clip) for every clip in the sequence."""
    for kind in ("video", "audio"):
        for i, track in enumerate(seq.get(kind, []), start=1):
            name = f"{'V' if kind == 'video' else 'A'}{i}"
            for clip in track.get("items", []):
                yield kind, name, clip


def find_clip(seq: dict, clip_id: int):
    for _kind, track, clip in clips_of(seq):
        if clip.get("clip") == clip_id:
            return track, clip
    return None, None


def item_index(project: dict) -> dict:
    """item id -> project row, walking bins."""
    out = {}

    def walk(node):
        for child in node.get("children", []) or []:
            if "item" in child:
                out[child["item"]] = child
            walk(child)

    walk(project.get("root", {}))
    return out


def summarize_sequence(seq: dict, items: dict | None = None, show_audio: bool = True) -> str:
    """The active sequence in about one line per clip; much smaller than the raw inspect JSON."""
    num, den = rate_of(seq)
    fps = nominal_fps(num, den)
    st = seq["settings"]
    tc = lambda t: frame_to_tc(ticks_to_frame(t, num, den), fps)  # noqa: E731
    lines = [
        f"SEQ {seq.get('name')} (id {seq.get('id')}) {st['width']}x{st['height']} "
        f"{num}/{den}fps dur {frame_to_tc(seq.get('durationFrames', 0), fps)}"
        + (f" in {tc(seq['in'])}" if seq.get("in") is not None else "")
        + (f" out {tc(seq['out'])}" if seq.get("out") is not None else "")
        + (f" playhead {tc(seq['playhead'])}" if seq.get("playhead") is not None else "")
    ]
    for kind in ("video", "audio"):
        if kind == "audio" and not show_audio:
            continue
        for i, track in enumerate(seq.get(kind, []), start=1):
            name = f"{'V' if kind == 'video' else 'A'}{i}"
            flags = "".join(
                f for f, on in (("L", track.get("locked")), ("M", track.get("muted")), ("off", not track.get("enabled", True))) if on
            )
            clips = track.get("items", [])
            lines.append(f"{name} {track.get('name', '')}{' [' + flags + ']' if flags else ''}: {len(clips)} clip(s)")
            for c in clips:
                extra = []
                if c.get("speed", 1.0) != 1.0:
                    extra.append(f"speed {c['speed']:g}")
                if c.get("reverse"):
                    extra.append("rev")
                if not c.get("enabled", True):
                    extra.append("disabled")
                if c.get("link") is not None:
                    extra.append(f"grp {c['link']}")
                fx = [e["effect"] for e in c.get("effects", []) if e["effect"] not in ("motion", "opacity", "time_remap", "volume", "channel_volume", "panner")]
                if fx:
                    extra.append("fx " + ",".join(fx))
                name_ = c.get("name") or (items or {}).get(c.get("item"), {}).get("name", "?")
                lines.append(
                    f"  c{c['clip']} item{c['item']} {name_!r} rec {frame_to_tc(c['startFrame'], fps)}-{frame_to_tc(c['endFrame'], fps)}"
                    f" ({c['endFrame'] - c['startFrame']}f) src {tc(c['sourceIn'])}-{tc(c['sourceOut'])}"
                    + (" " + " ".join(extra) if extra else "")
                )
            for tr in track.get("transitions", []):
                ends = f"c{tr.get('from')}->c{tr.get('to')}" if tr.get("from") and tr.get("to") else f"c{tr.get('from') or tr.get('to')}"
                lines.append(
                    f"  t{tr['id']} {tr.get('effect')} {ends} at {tc(tr['start'])} "
                    f"({ticks_to_frame(tr.get('duration', 0), num, den)}f {tr.get('align', '')})"
                )
    for m in seq.get("markers", []):
        dur = ticks_to_frame(m.get("duration", 0), num, den)
        lines.append(
            f"M{m['id']} {tc(m['start'])}{f' +{dur}f' if dur else ''} {m.get('color', '')} {m.get('name', '')!r}"
            + (f" — {m['comment']}" if m.get("comment") else "")
        )
    if seq.get("selection"):
        lines.append(f"selected: {seq['selection']}")
    return "\n".join(lines)


def same_path(p: str | os.PathLike) -> str:
    """Comparable form of a media path (Windows paths are case-insensitive)."""
    return os.path.normcase(str(Path(p).resolve()))


def backup_file(path: Path) -> Path | None:
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        rel = path.resolve().relative_to(ROOT)
    except ValueError:
        rel = Path(path.name)
    dest = BACKUP / stamp / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    return dest
