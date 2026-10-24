import re
from pathlib import Path
from zipfile import BadZipFile

import docx
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.ingestion.parsing._text import normalize, table_text
from app.ingestion.parsing.errors import DocumentParseError
from app.ingestion.parsing.models import Anchor, Block, BlockKind, ParsedDocument

_HEADING_STYLE = re.compile(r"Heading (\d)$")


def _table_rows(table: Table) -> list[list[str]]:
    rows = []
    for row in table.rows:
        seen: set[int] = set()  # merged cells repeat the same cell element
        cells = []
        for cell in row.cells:
            if id(cell._tc) not in seen:
                seen.add(id(cell._tc))
                cells.append(normalize(cell.text))
        rows.append(cells)
    return rows


def _paragraph_kind(paragraph: Paragraph) -> tuple[BlockKind, int | None]:
    style = paragraph.style.name if paragraph.style is not None else ""
    if style == "Title":
        return "heading", 0
    if match := _HEADING_STYLE.match(style):
        return "heading", int(match.group(1))
    p_pr = paragraph._p.pPr
    if style.startswith("List") or (p_pr is not None and p_pr.numPr is not None):
        return "list_item", None
    return "paragraph", None


def parse_docx(path: Path) -> ParsedDocument:
    try:
        document = docx.Document(str(path))
    except (PackageNotFoundError, BadZipFile, KeyError, ValueError) as e:
        raise DocumentParseError("The file is not a readable Word document.") from e

    title = normalize(document.core_properties.title or "") or None
    blocks: list[Block] = []
    sections: list[str] = []  # heading text per level; Title (level 0) stays out of the path

    for item in document.iter_inner_content():
        if isinstance(item, Table):
            kind, level, text = "table", None, table_text(_table_rows(item))
        else:
            kind, level = _paragraph_kind(item)
            text = normalize(item.text)
        if not text:
            continue
        if kind == "heading" and level == 0:
            title = title or text
        elif kind == "heading":
            sections = [*sections[: level - 1], text]
        anchor = Anchor(section_path=tuple(sections), paragraph_index=len(blocks))
        blocks.append(Block(kind=kind, text=text, heading_level=level, anchor=anchor))

    if not blocks:
        raise DocumentParseError("The Word document has no text.")
    return ParsedDocument(source_type="docx", title=title, blocks=tuple(blocks))
