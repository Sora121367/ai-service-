from pathlib import Path

import pymupdf

from app.ingestion.parsing._text import normalize
from app.ingestion.parsing.errors import DocumentParseError
from app.ingestion.parsing.models import Anchor, Block, ParsedDocument

_TEXT_BLOCK = 0


def section_paths(toc: list[list], page_count: int) -> list[tuple[str, ...]]:
    """Section path per page (index 0 unused) from the PDF's built-in outline.

    Page granularity: the last outline entry starting on or before a page applies to all of it.
    Finer, heading-based sections come from chapter detection later.
    """
    starts: dict[int, tuple[str, ...]] = {}
    stack: list[str] = []
    for level, title, page, *_ in toc:
        stack = [*stack[: level - 1], normalize(title)]
        if 1 <= page <= page_count:
            starts[page] = tuple(stack)
    paths: list[tuple[str, ...]] = [()]
    for page in range(1, page_count + 1):
        paths.append(starts.get(page, paths[-1]))
    return paths


def parse_pdf(path: Path) -> ParsedDocument:
    try:
        doc = pymupdf.open(path, filetype="pdf")
    except pymupdf.FileDataError as e:  # also covers empty files
        raise DocumentParseError("The file is not a readable PDF.") from e

    with doc:
        if doc.needs_pass:
            raise DocumentParseError("The PDF is password-protected.")
        if doc.page_count == 0:
            raise DocumentParseError("The PDF has no pages.")

        sections = section_paths(doc.get_toc(simple=True), doc.page_count)
        blocks: list[Block] = []
        needs_ocr: list[int] = []
        for number, page in enumerate(doc, start=1):
            anchor = Anchor(page=number, section_path=sections[number])
            texts = [
                text
                for *_, raw, _no, kind in page.get_text("blocks", sort=True)
                if kind == _TEXT_BLOCK and (text := normalize(raw))
            ]
            blocks.extend(Block(kind="paragraph", text=t, anchor=anchor) for t in texts)
            if not texts and page.get_images():
                needs_ocr.append(number)

        if not blocks and not needs_ocr:
            raise DocumentParseError("The PDF has no text or images.")
        title = normalize(doc.metadata.get("title") or "") or None
        return ParsedDocument(
            source_type="pdf",
            title=title,
            blocks=tuple(blocks),
            page_count=doc.page_count,
            pages_needing_ocr=tuple(needs_ocr),
        )
