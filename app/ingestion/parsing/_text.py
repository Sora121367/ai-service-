import codecs
import re
import unicodedata

from app.ingestion.parsing.errors import DocumentParseError

_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """NFC (Khmer and accented Latin compare equal), single spaces, no control characters.

    Zero-width spaces are kept: Khmer uses them as word breaks.
    """
    text = _WHITESPACE.sub(" ", unicodedata.normalize("NFC", text))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cc").strip()


def table_text(rows: list[list[str]]) -> str:
    """One line per row, cells joined by ' | '. Used for DOCX and PPTX tables."""
    return "\n".join(" | ".join(row) for row in rows if any(row))


def decode_text(data: bytes) -> str:
    """Text files arrive as UTF-8, UTF-16 (BOM) or Windows-1252; anything else is rejected."""
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16")
    if b"\x00" in data:
        raise DocumentParseError("The file contains binary data, not text.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1252")
    except UnicodeDecodeError as e:
        raise DocumentParseError("The text encoding is not supported; save it as UTF-8.") from e
