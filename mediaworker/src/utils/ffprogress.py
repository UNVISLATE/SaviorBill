"""Разбор machine-readable прогресса ffmpeg (``-progress pipe:1``).

Не парсинг человеческого stderr (хрупкие регулярки на строку вида
``frame=120 fps=30 time=00:01:23.45 ...``, которая меняет формат между
версиями ffmpeg) — используем встроенный в ffmpeg строгий key=value вывод,
предназначенный именно для программного чтения (``ffmpeg -progress <url>``).
Каждый блок завершается строкой ``progress=continue``/``progress=end``.
"""

from __future__ import annotations

from dataclasses import dataclass

_NA = ("", "N/A", "n/a")


@dataclass(slots=True)
class ProgressSnapshot:
    """Один снимок прогресса кодирования (между двумя ``progress=`` строками)."""

    frame: int | None
    fps: float | None
    bitrate_kbps: float | None
    out_time_sec: float | None
    speed: float | None
    percent: float | None
    eta_sec: float | None
    done: bool


def _parse_float(raw: str | None) -> float | None:
    if raw is None or raw in _NA:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


class ProgressParser:
    """Накопитель одного блока построчного ``-progress`` вывода ffmpeg."""

    def __init__(self, total_duration_sec: float | None = None) -> None:
        self.total_duration_sec = total_duration_sec
        self._fields: dict[str, str] = {}

    def feed_line(self, line: str) -> ProgressSnapshot | None:
        """Накопить одну строку ``key=value``; вернуть снимок на конце блока."""
        line = line.strip()
        if not line or "=" not in line:
            return None
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key != "progress":
            self._fields[key] = value
            return None
        snapshot = self._build_snapshot(done=value == "end")
        self._fields = {}
        return snapshot

    def _build_snapshot(self, *, done: bool) -> ProgressSnapshot:
        frame = _parse_float(self._fields.get("frame"))
        fps = _parse_float(self._fields.get("fps"))
        bitrate_raw = self._fields.get("bitrate")
        bitrate_kbps = None
        if bitrate_raw and bitrate_raw not in _NA:
            bitrate_kbps = _parse_float(bitrate_raw.removesuffix("kbits/s"))
        out_time_us = _parse_float(self._fields.get("out_time_us"))
        out_time_sec = out_time_us / 1_000_000 if out_time_us is not None else None
        speed_raw = self._fields.get("speed")
        speed = _parse_float(speed_raw.rstrip("x")) if speed_raw and speed_raw not in _NA else None

        percent: float | None = None
        eta_sec: float | None = None
        if out_time_sec is not None and self.total_duration_sec and self.total_duration_sec > 0:
            percent = min(100.0, max(0.0, out_time_sec / self.total_duration_sec * 100))
            remaining = max(0.0, self.total_duration_sec - out_time_sec)
            if speed and speed > 0:
                eta_sec = remaining / speed
        if done:
            percent = 100.0
            eta_sec = 0.0

        return ProgressSnapshot(
            frame=int(frame) if frame is not None else None,
            fps=fps,
            bitrate_kbps=bitrate_kbps,
            out_time_sec=out_time_sec,
            speed=speed,
            percent=percent,
            eta_sec=eta_sec,
            done=done,
        )


__all__ = ["ProgressParser", "ProgressSnapshot"]
