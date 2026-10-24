"""One structured format for every parsed file. Anchors keep what citations need (spec Section 5)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

SourceType = Literal["pdf", "docx", "pptx", "txt", "video"]  # "video": a subtitle file (SRT/VTT)
BlockKind = Literal["heading", "paragraph", "list_item", "table", "notes"]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Anchor(_Frozen):
    """Where a block lives in its source. Page and slide numbers are 1-based."""

    page: int | None = None
    slide: int | None = None
    section_path: tuple[str, ...] = ()  # headings above the block, outermost first
    paragraph_index: int | None = None
    start_seconds: float | None = None  # timed sources (subtitles, transcripts)
    end_seconds: float | None = None


class Block(_Frozen):
    kind: BlockKind
    text: str
    heading_level: int | None = None
    anchor: Anchor


class ParsedDocument(_Frozen):
    source_type: SourceType
    title: str | None = None
    blocks: tuple[Block, ...]
    page_count: int | None = None
    slide_count: int | None = None
    pages_needing_ocr: tuple[int, ...] = ()  # pages (or slides) with images but no text
