"""Local-only OCR. Never persist images or recognized text."""

import io
import re
from typing import Any

import pytesseract
from PIL import Image, ImageOps, UnidentifiedImageError

from .rules import RuleError, parse_expiry

DATE_PATTERN = r"(?<!\d)(?:\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2}|\d{2}/\d{4})(?!\d)"


class UploadError(ValueError):
    def __init__(self, code: str, status: int, message: str):
        self.code, self.status = code, status
        super().__init__(message)


def candidate_from_text(text: str) -> dict[str, Any]:
    matches = list(re.finditer(DATE_PATTERN, text))
    candidates = []
    for match in matches:
        try:
            value = parse_expiry(match.group(), True)
        except RuleError:
            continue
        before = text[max(0, match.start() - 35) : match.start()].upper()
        # Prefer explicit expiry context; do not silently treat MFG as expiry.
        expiry = bool(re.search(r"(?:EXP(?:IRY)?|USE BY|BEST BEFORE|ГОДЕН ДО|СРОК ДО)\s*[:.\-]?\s*$", before))
        manufacturing = bool(re.search(r"(?:MFG|MFD|ПРОИЗВЕДЕНО|ДАТА ИЗГОТОВЛЕНИЯ)\s*[:.\-]?\s*$", before))
        candidates.append((value, expiry, manufacturing))
    explicit = {c[0]["input_value"]: c[0] for c in candidates if c[1] and not c[2]}
    unique = {c[0]["input_value"]: c[0] for c in candidates if not c[2]}
    chosen = list(explicit.values()) if explicit else list(unique.values())
    if len(chosen) == 1 and (explicit or len(matches) == 1):
        return {"status": "CANDIDATE", "candidate": chosen[0], "message": "Проверьте дату на упаковке и подтвердите её."}
    if matches:
        return {"status": "AMBIGUOUS", "candidate": None, "message": "Маркировка неоднозначна. Введите срок вручную."}
    return {"status": "NOT_READ", "candidate": None, "message": "Дата не распознана. Повторите снимок или введите вручную."}


def recognize(data: bytes) -> dict[str, Any]:
    if len(data) > 5 * 1024 * 1024:
        raise UploadError("FILE_TOO_LARGE", 413, "Максимальный размер — 5 MiB.")
    if not (data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff")):
        raise UploadError("UNSUPPORTED_IMAGE", 415, "Загрузите JPEG или PNG.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > 12_000_000:
                raise UploadError("IMAGE_TOO_LARGE", 422, "Максимум 12 мегапикселей.")
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            prepared = ImageOps.exif_transpose(image).convert("L")
            prepared.thumbnail((2200, 2200))
            prepared = ImageOps.autocontrast(prepared)
            text = pytesseract.image_to_string(prepared, config="--psm 6", timeout=12)
        return candidate_from_text(text)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise UploadError("INVALID_IMAGE", 422, "Файл повреждён. Загрузите другой снимок.") from exc
    except pytesseract.TesseractNotFoundError as exc:
        raise UploadError("OCR_UNAVAILABLE", 503, "Tesseract недоступен. Введите дату вручную.") from exc
    except RuntimeError as exc:
        raise UploadError("OCR_TIMEOUT", 504, "Распознавание заняло слишком много времени. Введите дату вручную.") from exc
