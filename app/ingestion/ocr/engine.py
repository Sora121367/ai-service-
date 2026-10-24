"""The OCR engine behind a small interface, so the pipeline and its tests don't need Paddle.

The local implementation is `app.clients.paddle_ocr.PaddleOcrEngine`.
"""

from typing import Protocol


class OcrEngine(Protocol):
    def recognize(self, image: bytes) -> list[str]:
        """Text lines of one encoded image (PNG, JPEG...), in reading order."""
