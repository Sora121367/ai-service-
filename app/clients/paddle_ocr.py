class PaddleOcrEngine:
    """PaddleOCR running locally (spec Section 3: fully local AI, no cloud OCR).

    Implements `app.ingestion.ocr.OcrEngine`. Models load on first use: importing this module
    stays cheap, and the first call downloads the model files if they are missing. `lang` is a
    PaddleOCR language code; Khmer support depends on the PaddleOCR release and is best effort
    (spec Section 9).
    """

    def __init__(self, lang: str) -> None:
        self._lang = lang
        self._ocr = None

    def _load(self):
        if self._ocr is None:
            from paddleocr import PaddleOCR  # optional dependency: `uv sync --extra ocr`

            self._ocr = PaddleOCR(
                lang=self._lang,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                enable_mkldnn=False,  # oneDNN crashes on some CPU builds (Windows)
            )
        return self._ocr

    def recognize(self, image: bytes) -> list[str]:
        import cv2
        import numpy as np

        array = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        if array is None:
            return []
        lines: list[str] = []
        for result in self._load().predict(array):
            lines.extend(result["rec_texts"])
        return lines
