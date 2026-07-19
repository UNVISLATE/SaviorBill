"""Юнит-тесты парсера machine-readable прогресса ffmpeg (``-progress pipe:1``)."""

from utils.ffprogress import ProgressParser


def _feed(parser: ProgressParser, block: str):
    """Отдать построчно один ``-progress`` блок, вернуть финальный снимок."""
    snapshot = None
    for line in block.strip().splitlines():
        result = parser.feed_line(line)
        if result is not None:
            snapshot = result
    return snapshot


def test_intermediate_block_computes_percent_and_eta():
    parser = ProgressParser(total_duration_sec=100.0)
    block = """
        frame=120
        fps=30.0
        bitrate=512.3kbits/s
        out_time_us=25000000
        speed=1.0x
        progress=continue
    """
    snap = _feed(parser, block)
    assert snap is not None
    assert snap.frame == 120
    assert snap.fps == 30.0
    assert snap.bitrate_kbps == 512.3
    assert snap.out_time_sec == 25.0
    assert snap.speed == 1.0
    assert snap.percent == 25.0
    assert snap.eta_sec == 75.0
    assert snap.done is False


def test_final_block_reports_done_and_full_percent():
    parser = ProgressParser(total_duration_sec=10.0)
    block = """
        out_time_us=10000000
        speed=2.0x
        progress=end
    """
    snap = _feed(parser, block)
    assert snap is not None
    assert snap.done is True
    assert snap.percent == 100.0
    assert snap.eta_sec == 0.0


def test_missing_total_duration_yields_no_percent_or_eta():
    parser = ProgressParser(total_duration_sec=None)
    block = """
        out_time_us=5000000
        speed=1.0x
        progress=continue
    """
    snap = _feed(parser, block)
    assert snap is not None
    assert snap.percent is None
    assert snap.eta_sec is None


def test_na_fields_parsed_as_none():
    parser = ProgressParser(total_duration_sec=100.0)
    block = """
        speed=N/A
        bitrate=N/A
        progress=continue
    """
    snap = _feed(parser, block)
    assert snap is not None
    assert snap.speed is None
    assert snap.bitrate_kbps is None
    assert snap.percent is None
    assert snap.eta_sec is None


def test_zero_speed_avoids_eta_division_by_zero():
    parser = ProgressParser(total_duration_sec=100.0)
    block = """
        out_time_us=10000000
        speed=0.0x
        progress=continue
    """
    snap = _feed(parser, block)
    assert snap is not None
    assert snap.percent == 10.0
    assert snap.eta_sec is None


def test_blank_and_malformed_lines_are_ignored():
    parser = ProgressParser(total_duration_sec=100.0)
    assert parser.feed_line("") is None
    assert parser.feed_line("garbage without equals") is None
