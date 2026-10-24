import pymupdf
import pytest

from app.ingestion.parsing import DocumentParseError, parse_document


def save(doc: pymupdf.Document, tmp_path, **save_options):
    path = tmp_path / "doc.pdf"
    doc.save(path, **save_options)
    return path


def text_pdf(pages: list[list[str]]) -> pymupdf.Document:
    doc = pymupdf.open()
    for paragraphs in pages:
        page = doc.new_page()
        for i, text in enumerate(paragraphs):
            page.insert_text((72, 100 + 200 * i), text)
    return doc


def image_page(doc: pymupdf.Document) -> None:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)
    pix.clear_with(200)
    doc.new_page().insert_image(pymupdf.Rect(72, 72, 272, 272), pixmap=pix)


def test_extracts_text_blocks_with_page_anchors(tmp_path):
    doc = text_pdf([["Intro paragraph", "Second block"], ["Page two text"]])
    doc.set_metadata({"title": "Lecture 1"})
    parsed = parse_document(save(doc, tmp_path), "pdf")

    assert [(b.anchor.page, b.text) for b in parsed.blocks] == [
        (1, "Intro paragraph"),
        (1, "Second block"),
        (2, "Page two text"),
    ]
    assert parsed.page_count == 2
    assert parsed.title == "Lecture 1"
    assert parsed.pages_needing_ocr == ()


def test_section_paths_follow_the_outline(tmp_path):
    doc = text_pdf([["a"], ["b"], ["c"], ["d"]])
    doc.set_toc([[1, "Chapter 1", 1], [2, "1.1 Basics", 2], [1, "Chapter 2", 4]])
    parsed = parse_document(save(doc, tmp_path), "pdf")

    assert [b.anchor.section_path for b in parsed.blocks] == [
        ("Chapter 1",),
        ("Chapter 1", "1.1 Basics"),
        ("Chapter 1", "1.1 Basics"),
        ("Chapter 2",),
    ]


def test_no_outline_means_empty_section_path(tmp_path):
    parsed = parse_document(save(text_pdf([["a"]]), tmp_path), "pdf")
    assert parsed.blocks[0].anchor.section_path == ()
    assert parsed.title is None


def test_flags_image_only_pages_for_ocr(tmp_path):
    doc = text_pdf([["Text page"]])
    image_page(doc)
    parsed = parse_document(save(doc, tmp_path), "pdf")

    assert parsed.pages_needing_ocr == (2,)
    assert [b.anchor.page for b in parsed.blocks] == [1]


def test_scanned_pdf_parses_with_no_blocks(tmp_path):
    doc = pymupdf.open()
    image_page(doc)
    parsed = parse_document(save(doc, tmp_path), "pdf")
    assert parsed.blocks == ()
    assert parsed.pages_needing_ocr == (1,)


def test_rejects_password_protected_pdf(tmp_path):
    path = save(
        text_pdf([["secret"]]),
        tmp_path,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw="user",
        owner_pw="owner",
    )
    with pytest.raises(DocumentParseError, match="password"):
        parse_document(path, "pdf")


def test_rejects_blank_pdf(tmp_path):
    doc = pymupdf.open()
    doc.new_page()
    with pytest.raises(DocumentParseError):
        parse_document(save(doc, tmp_path), "pdf")


@pytest.mark.parametrize("data", [b"", b"not a pdf"], ids=["empty", "corrupt"])
def test_rejects_unreadable_files(tmp_path, data):
    path = tmp_path / "bad.pdf"
    path.write_bytes(data)
    with pytest.raises(DocumentParseError):
        parse_document(path, "pdf")
