"""Turn a stored file into a ParsedDocument with citation anchors (spec Section 5, Parsing).

File text is data, never instructions: parsers only extract it.
"""

from collections.abc import Callable
from pathlib import Path

from app.ingestion.parsing.docx import parse_docx
from app.ingestion.parsing.errors import DocumentParseError, ParseError, UnsupportedFormatError
from app.ingestion.parsing.models import Anchor, Block, ParsedDocument, SourceType
from app.ingestion.parsing.pdf import parse_pdf
from app.ingestion.parsing.pptx import parse_pptx
from app.ingestion.parsing.subtitles import parse_subtitles
from app.ingestion.parsing.txt import parse_txt

__all__ = [
    "Anchor",
    "Block",
    "DocumentParseError",
    "ParseError",
    "ParsedDocument",
    "SourceType",
    "UnsupportedFormatError",
    "parse_document",
]

_PARSERS: dict[str, Callable[[Path], ParsedDocument]] = {
    "docx": parse_docx,
    "pdf": parse_pdf,
    "pptx": parse_pptx,
    "srt": parse_subtitles,
    "txt": parse_txt,
    "vtt": parse_subtitles,
}


def parse_document(path: Path, source_type: SourceType | str) -> ParsedDocument:
    parser = _PARSERS.get(source_type)
    if parser is None:
        raise UnsupportedFormatError(f"Files of type {source_type!r} can't be processed yet.")
    return parser(path)
