import importlib.util

import pymupdf
import pytest


@pytest.mark.skipif(
    importlib.util.find_spec("paddleocr") is None,
    reason="PaddleOCR not installed (uv sync --extra ocr)",
)
def test_paddle_engine_reads_rendered_text():
    from app.clients.paddle_ocr import PaddleOcrEngine

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), "Hello InsightHub", fontsize=32)
    image = doc[0].get_pixmap(dpi=200).tobytes("png")
    assert "InsightHub" in " ".join(PaddleOcrEngine("en").recognize(image))
