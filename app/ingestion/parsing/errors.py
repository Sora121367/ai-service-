class ParseError(Exception):
    """A file could not be turned into a ParsedDocument; the message is safe to show as job status."""


class UnsupportedFormatError(ParseError):
    """No parser exists for the source type."""


class DocumentParseError(ParseError):
    """The file is corrupt, encrypted, empty or not of the declared type."""
