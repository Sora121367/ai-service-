import html
import re
from pathlib import Path

from app.ingestion.parsing._text import decode_text, normalize
from app.ingestion.parsing.errors import DocumentParseError
from app.ingestion.parsing.models import Anchor, Block, ParsedDocument

# SRT "00:00:01,500" and VTT "00:01.500" / "00:00:01.500" (hours optional in VTT).
_TIMING = re.compile(
    r"^\s*(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})"
)
_TAG = re.compile(r"<[^>]*>")  # <i>, <c.class>, <v Name>, inline <00:01.200> timestamps
_BLANK_LINE = re.compile(r"\n[ \t]*\n")


def _seconds(hours: str | None, minutes: str, seconds: str, millis: str) -> float:
    return (
        int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int(millis.ljust(3, "0")) / 1000
    )


def _cue_text(lines: list[str]) -> str:
    return normalize(html.unescape(_TAG.sub("", " ".join(lines))))


def parse_subtitles(path: Path) -> ParsedDocument:
    """SRT or WebVTT: one block per cue, with its start and end time in seconds.

    Header, NOTE, STYLE and REGION blocks are skipped. Cues that overlap or run out of order
    are kept as given; the caller decides how to cut passages.
    """
    text = decode_text(path.read_bytes()).replace("\r\n", "\n").replace("\r", "\n")
    blocks: list[Block] = []
    for raw in _BLANK_LINE.split(text.lstrip("\ufeff")):
        lines = raw.strip("\n").split("\n")
        timing_at = next((i for i, line in enumerate(lines) if _TIMING.match(line)), None)
        if timing_at is None or timing_at > 1:  # at most one line (the cue id) precedes timing
            continue
        match = _TIMING.match(lines[timing_at])
        assert match is not None
        start = _seconds(*match.group(1, 2, 3, 4))
        end = _seconds(*match.group(5, 6, 7, 8))
        if end < start:
            continue
        if cue := _cue_text(lines[timing_at + 1 :]):
            anchor = Anchor(paragraph_index=len(blocks), start_seconds=start, end_seconds=end)
            blocks.append(Block(kind="paragraph", text=cue, anchor=anchor))
    if not blocks:
        raise DocumentParseError("The subtitle file has no readable cues.")
    return ParsedDocument(source_type="video", blocks=tuple(blocks))
