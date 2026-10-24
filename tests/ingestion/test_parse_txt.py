import codecs

import pytest

from app.ingestion.parsing import DocumentParseError, parse_document

KHMER = "សួស្តី\u200bពិភពលោក"  # zero-width space is a Khmer word break


def write(tmp_path, data: bytes):
    path = tmp_path / "notes.txt"
    path.write_bytes(data)
    return path


def test_splits_paragraphs_on_blank_lines(tmp_path):
    path = write(tmp_path, b"First line\nwraps here.\r\n\r\n  \n\nSecond   paragraph.\n")
    doc = parse_document(path, "txt")
    assert [b.text for b in doc.blocks] == ["First line wraps here.", "Second paragraph."]
    assert [b.anchor.paragraph_index for b in doc.blocks] == [0, 1]
    assert {b.kind for b in doc.blocks} == {"paragraph"}
    assert doc.source_type == "txt"


def test_keeps_khmer_text_and_word_breaks(tmp_path):
    doc = parse_document(write(tmp_path, KHMER.encode("utf-8")), "txt")
    assert doc.blocks[0].text == KHMER


def test_normalizes_to_nfc(tmp_path):
    doc = parse_document(write(tmp_path, "Café".encode()), "txt")
    assert doc.blocks[0].text == "Café"


@pytest.mark.parametrize(
    "data",
    [
        codecs.BOM_UTF8 + b"Hello",
        "Hello".encode("utf-16"),
        "Héllo".encode("cp1252"),
    ],
    ids=["utf8-bom", "utf16", "cp1252"],
)
def test_decodes_common_encodings(tmp_path, data):
    assert parse_document(write(tmp_path, data), "txt").blocks[0].text.endswith("llo")


def test_strips_control_characters(tmp_path):
    doc = parse_document(write(tmp_path, b"bell\x07 here"), "txt")
    assert doc.blocks[0].text == "bell here"


@pytest.mark.parametrize(
    "data", [b"", b"  \n\n\t ", b"\x89PNG\r\n\x1a\n\x00\x00"], ids=["empty", "blank", "binary"]
)
def test_rejects_files_without_text(tmp_path, data):
    with pytest.raises(DocumentParseError):
        parse_document(write(tmp_path, data), "txt")
