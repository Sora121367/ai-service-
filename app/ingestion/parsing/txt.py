import re
from pathlib import Path

from app.ingestion.parsing._text import decode_text, normalize
from app.ingestion.parsing.errors import DocumentParseError
from app.ingestion.parsing.models import Anchor, Block, ParsedDocument

_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")


def parse_txt(path: Path) -> ParsedDocument:
    text = decode_text(path.read_bytes()).replace("\r\n", "\n").replace("\r", "\n")
    blocks: list[Block] = []
    for raw in _PARAGRAPH_BREAK.split(text):
        if paragraph := normalize(raw):
            anchor = Anchor(paragraph_index=len(blocks))
            blocks.append(Block(kind="paragraph", text=paragraph, anchor=anchor))
    if not blocks:
        raise DocumentParseError("The file has no text.")
    return ParsedDocument(source_type="txt", blocks=tuple(blocks))
