"""Split a ParsedDocument into chunks that each cite one place (spec Section 5, Chunking).

A chunk never crosses a page, slide or section, so its anchor is exact and a citation can point
at it. Size is counted in characters: the embedding model (and its tokenizer) is not chosen yet.
"""

import re
from collections.abc import Iterator

from pydantic import BaseModel, ConfigDict

from app.ingestion.parsing.models import Anchor, Block, ParsedDocument, SourceType

DEFAULT_MAX_CHARS = 1200
MIN_PASSAGE_SECONDS = 30  # timed sources: passages of 30-60 s, cut at a sentence end (spec Sec. 5)
MAX_PASSAGE_SECONDS = 60
_SEPARATOR = "\n\n"
_SENTENCE_END_AT_EOL = re.compile(r"[.!?។៕][\"'”’)]*$")
_SENTENCE_END = re.compile(r"(?<=[.!?។៕])\s+")  # includes the Khmer full stops


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    index: int  # position in the document, starting at 0
    text: str
    source_type: SourceType
    anchor: Anchor  # of the first block; page, slide and section_path hold for the whole chunk


def _hard_split(text: str, max_chars: int) -> Iterator[str]:
    """Last resort for text with no sentence ends: cut at spaces, or mid-word if there are none."""
    while len(text) > max_chars:
        cut = text.rfind(" ", 0, max_chars + 1)
        if cut <= 0:
            cut = max_chars
        yield text[:cut].strip()
        text = text[cut:].strip()
    if text:
        yield text


def _split_text(text: str, max_chars: int) -> Iterator[str]:
    """Pieces of at most max_chars, preferring to cut after a sentence, then at a line."""
    current = ""
    for sentence in text.split("\n"):
        for part in _SENTENCE_END.split(sentence):
            if len(part) > max_chars:
                if current:
                    yield current
                    current = ""
                yield from _hard_split(part, max_chars)
            elif current and len(current) + 1 + len(part) > max_chars:
                yield current
                current = part
            else:
                current = f"{current} {part}" if current else part
    if current:
        yield current


def _group_key(block: Block) -> tuple[int | None, int | None, tuple[str, ...]]:
    return block.anchor.page, block.anchor.slide, block.anchor.section_path


def _chunk_timed(document: ParsedDocument, max_chars: int) -> list[Chunk]:
    """Passages of subtitle cues. The anchor spans the passage: first start to last end."""
    chunks: list[Chunk] = []
    texts: list[str] = []
    first: Anchor | None = None
    end = 0.0

    def flush() -> None:
        nonlocal texts, first
        if texts and first is not None:
            anchor = first.model_copy(update={"end_seconds": end})
            chunks.append(
                Chunk(
                    index=len(chunks),
                    text=" ".join(texts),
                    source_type=document.source_type,
                    anchor=anchor,
                )
            )
        texts, first = [], None

    for block in document.blocks:
        anchor = block.anchor
        assert anchor.start_seconds is not None and anchor.end_seconds is not None
        for piece in _split_text(block.text, max_chars):
            too_long = first is not None and anchor.end_seconds - first.start_seconds > (
                MAX_PASSAGE_SECONDS
            )
            if texts and (too_long or len(" ".join(texts)) + 1 + len(piece) > max_chars):
                flush()
            if first is None:
                first = anchor
            texts.append(piece)
            end = anchor.end_seconds
        if (
            first is not None
            and end - first.start_seconds >= MIN_PASSAGE_SECONDS
            and _SENTENCE_END_AT_EOL.search(texts[-1])
        ):
            flush()
    flush()
    return chunks


def chunk_document(document: ParsedDocument, max_chars: int = DEFAULT_MAX_CHARS) -> list[Chunk]:
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    if document.blocks and all(b.anchor.start_seconds is not None for b in document.blocks):
        return _chunk_timed(document, max_chars)

    chunks: list[Chunk] = []

    def emit(text: str, anchor: Anchor) -> None:
        chunks.append(
            Chunk(index=len(chunks), text=text, source_type=document.source_type, anchor=anchor)
        )

    pending: list[str] = []
    pending_anchor: Anchor | None = None

    def flush() -> None:
        nonlocal pending, pending_anchor
        if pending and pending_anchor is not None:
            emit(_SEPARATOR.join(pending), pending_anchor)
        pending, pending_anchor = [], None

    previous_key = None
    for block in document.blocks:
        key = _group_key(block)
        if key != previous_key:
            flush()
            previous_key = key
        pieces = (
            [block.text] if len(block.text) <= max_chars else _split_text(block.text, max_chars)
        )
        for piece in pieces:
            size = sum(len(t) for t in pending) + len(_SEPARATOR) * len(pending)
            if pending and size + len(piece) > max_chars:
                flush()
            if pending_anchor is None:
                pending_anchor = block.anchor
            pending.append(piece)
    flush()
    return chunks
