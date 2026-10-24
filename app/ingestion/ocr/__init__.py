"""Fill pages that had only images with the text OCR reads from them (spec Section 5, OCR)."""

from collections.abc import Iterator
from pathlib import Path

import pymupdf

from app.ingestion.ocr.engine import OcrEngine
from app.ingestion.ocr.images import DEFAULT_PDF_DPI, pdf_page_images, pptx_slide_images
from app.ingestion.parsing._text import normalize
from app.ingestion.parsing.models import Anchor, Block, ParsedDocument
from app.ingestion.parsing.pdf import section_paths

__all__ = ["OcrEngine", "run_ocr"]


def _page_images(
    path: Path, document: ParsedDocument, pdf_dpi: int
) -> Iterator[tuple[int, list[bytes]]]:
    if document.source_type == "pdf":
        return pdf_page_images(path, document.pages_needing_ocr, pdf_dpi)
    if document.source_type == "pptx":
        return pptx_slide_images(path, document.pages_needing_ocr)
    return iter(())


def _anchor(document: ParsedDocument, number: int, outline: list[tuple[str, ...]]) -> Anchor:
    if document.source_type == "pdf":
        return Anchor(page=number, section_path=outline[number])
    # A slide keeps the section path (its title) of the blocks the parser already found.
    known = next((b.anchor for b in document.blocks if b.anchor.slide == number), None)
    return Anchor(slide=number, section_path=known.section_path if known else ())


def _outline(path: Path, document: ParsedDocument) -> list[tuple[str, ...]]:
    if document.source_type != "pdf":
        return []
    with pymupdf.open(path, filetype="pdf") as doc:
        return section_paths(doc.get_toc(simple=True), doc.page_count)


def _position(block: Block) -> int:
    return block.anchor.page or block.anchor.slide or 0


def run_ocr(
    path: Path, document: ParsedDocument, engine: OcrEngine, pdf_dpi: int = DEFAULT_PDF_DPI
) -> ParsedDocument:
    """A copy of `document` with one paragraph block per OCR'd image.

    Pages where nothing was read stay in `pages_needing_ocr`, so the caller can tell the user.
    Recognized text is data, never instructions, like any other file text.
    """
    if not document.pages_needing_ocr:
        return document

    outline = _outline(path, document)
    added: list[Block] = []
    unread = set(document.pages_needing_ocr)
    for number, images in _page_images(path, document, pdf_dpi):
        anchor = _anchor(document, number, outline)
        for image in images:
            lines = (normalize(line) for line in engine.recognize(image))
            if text := "\n".join(line for line in lines if line):
                added.append(Block(kind="paragraph", text=text, anchor=anchor))
                unread.discard(number)

    # Stable sort: OCR text lands after a slide's own blocks, and before the next page.
    blocks = sorted([*document.blocks, *added], key=_position)
    return document.model_copy(
        update={"blocks": tuple(blocks), "pages_needing_ocr": tuple(sorted(unread))}
    )
