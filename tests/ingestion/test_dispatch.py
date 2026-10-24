import pytest

from app.ingestion.parsing import ParseError, UnsupportedFormatError, parse_document


@pytest.mark.parametrize("source_type", ["exe", "mp4", ""])
def test_unknown_source_type_is_unsupported(tmp_path, source_type):
    path = tmp_path / "file"
    path.write_bytes(b"x")
    with pytest.raises(UnsupportedFormatError):
        parse_document(path, source_type)


def test_parse_errors_share_a_base_class():
    assert issubclass(UnsupportedFormatError, ParseError)
