from __future__ import annotations

import re
from pathlib import Path


FIELD_ALIASES: dict[str, str] = {
    "name": "name",
    "full name": "name",
    "phone": "phone",
    "mobile": "phone",
    "mobile no": "phone",
    "mobile number": "phone",
    "address": "address",
    "consumer number": "consumer_number",
    "consumer no": "consumer_number",
    "consumer id": "consumer_number",
    "consumer": "consumer_number",
}


async def process_document(file_path: str) -> dict:
    """
    Extract structured fields from a document.

    The document is expected to follow a consistent template with key/value
    labels. Unknown keys are also preserved in the returned dictionary.
    """
    text = _extract_text(file_path)
    data = _parse_template_fields(text)
    data["_source_file"] = Path(file_path).name
    return data


def _extract_text(file_path: str) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")

    if suffix == ".pdf":
        return _extract_pdf_text(path)

    if suffix in {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}:
        return _extract_image_text(path)

    raise ValueError(f"Unsupported file type: {suffix or 'unknown'}")


def _extract_pdf_text(path: Path) -> str:
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError(
            "PDF extraction requires the optional 'pdfplumber' dependency."
        ) from exc

    chunks: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text:
                chunks.append(page_text)
    return "\n".join(chunks)


def _extract_image_text(path: Path) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "Image OCR requires the optional 'pytesseract' and 'Pillow' dependencies."
        ) from exc

    with Image.open(path) as image:
        return pytesseract.image_to_string(image)


def _parse_template_fields(text: str) -> dict:
    """
    Parse key/value pairs from extracted text.

    The parser accepts formats like:
    - Name: Bhargab
    - Name - Bhargab
    - Name Bhargab
    """
    data: dict[str, str] = {}
    current_key: str | None = None
    current_value_lines: list[str] = []

    def commit_current() -> None:
        nonlocal current_key, current_value_lines
        if current_key and current_value_lines:
            value = " ".join(part.strip() for part in current_value_lines if part.strip()).strip()
            if value:
                data[current_key] = value
        current_key = None
        current_value_lines = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        key, value = _split_key_value(line)
        if key:
            commit_current()
            normalized_key = _normalize_key(key)
            current_key = normalized_key
            current_value_lines = [value] if value else []
            if value:
                commit_current()
            continue

        if current_key:
            current_value_lines.append(line)

    commit_current()
    return data


def _split_key_value(line: str) -> tuple[str | None, str]:
    for separator in (":", "-", "—"):
        if separator in line:
            left, right = line.split(separator, 1)
            left = left.strip()
            right = right.strip()
            if left:
                return left, right

    match = re.match(r"^([A-Za-z][A-Za-z0-9 _/-]{1,40})\s+(.+)$", line)
    if match:
        left, right = match.group(1).strip(), match.group(2).strip()
        if _normalize_key(left) in FIELD_ALIASES:
            return left, right

    return None, ""


def _normalize_key(key: str) -> str:
    normalized = re.sub(r"\s+", " ", key.strip().lower())
    return FIELD_ALIASES.get(normalized, re.sub(r"[^a-z0-9_]+", "_", normalized).strip("_"))
