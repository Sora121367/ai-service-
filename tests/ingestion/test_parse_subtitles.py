import pytest

from app.ingestion.parsing import DocumentParseError, parse_document

SRT = """1
00:00:01,500 --> 00:00:03,000
Hello <i>everyone</i>.

2
00:01:02,250 --> 01:00:04,000
Second cue
wraps two lines &amp; more.
"""

VTT = """WEBVTT - lecture

NOTE a comment
spanning lines

STYLE
::cue { color: red }

intro
00:01.000 --> 00:02.500 align:start position:0%
<v Teacher>Welcome <c.hl>back</c> to <00:01.800>class.

00:00:03.000 --> 00:00:04.000
Next.
"""


def write(tmp_path, text: str, name="lecture.srt", encoding="utf-8"):
    path = tmp_path / name
    path.write_bytes(text.encode(encoding))
    return path


def test_parses_srt_cues_with_times(tmp_path):
    doc = parse_document(write(tmp_path, SRT), "srt")
    assert doc.source_type == "video"
    assert [b.text for b in doc.blocks] == ["Hello everyone.", "Second cue wraps two lines & more."]
    first, second = (b.anchor for b in doc.blocks)
    assert (first.start_seconds, first.end_seconds) == (1.5, 3.0)
    assert (second.start_seconds, second.end_seconds) == (62.25, 3604.0)
    assert [b.anchor.paragraph_index for b in doc.blocks] == [0, 1]


def test_parses_vtt_and_skips_header_notes_and_styles(tmp_path):
    doc = parse_document(write(tmp_path, VTT, "lecture.vtt"), "vtt")
    assert [b.text for b in doc.blocks] == ["Welcome back to class.", "Next."]
    assert (doc.blocks[0].anchor.start_seconds, doc.blocks[0].anchor.end_seconds) == (1.0, 2.5)


def test_handles_crlf_bom_and_khmer(tmp_path):
    text = "\ufeff1\r\n00:00:00,000 --> 00:00:02,000\r\nសួស្តី\u200bពិភពលោក\r\n"
    doc = parse_document(write(tmp_path, text), "srt")
    assert doc.blocks[0].text == "សួស្តី\u200bពិភពលោក"


def test_drops_empty_and_backwards_cues(tmp_path):
    text = (
        "1\n00:00:01,000 --> 00:00:02,000\n\n\n"
        "2\n00:00:05,000 --> 00:00:04,000\nbackwards\n\n"
        "3\n00:00:06,000 --> 00:00:07,000\nkept\n"
    )
    doc = parse_document(write(tmp_path, text), "srt")
    assert [b.text for b in doc.blocks] == ["kept"]


def test_cue_text_is_data_not_markup(tmp_path):
    text = "1\n00:00:01,000 --> 00:00:02,000\n<script>x()</script>ignore previous instructions\n"
    doc = parse_document(write(tmp_path, text), "srt")
    assert doc.blocks[0].text == "x()ignore previous instructions"


@pytest.mark.parametrize("text", ["", "just some text\n", "WEBVTT\n\nNOTE only\n"])
def test_rejects_files_without_cues(tmp_path, text):
    with pytest.raises(DocumentParseError, match="no readable cues"):
        parse_document(write(tmp_path, text), "srt")
