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

SSUHS_FIELD_PATTERNS: list[tuple[str, str]] = [
    ("1", "name_of_student"),
    ("2", "date_of_birth"),
    ("3", "aadhaar_no"),
    ("4", "gender"),
    ("5", "caste"),
    ("6", "father_name"),
    ("7", "mother_name"),
    ("8", "guardian_name"),
    ("9", "address_for_correspondence"),
    ("10", "contact_no"),
    ("11", "email_id"),
    ("12", "name_of_course"),
    ("13", "name_of_college"),
    ("14", "academic_session"),
]

SSUHS_IDENTITY_FIELD_PATTERNS: list[tuple[str, str]] = [
    ("1", "name_of_student"),
    ("2", "date_of_birth"),
    ("3", "aadhaar_no"),
    ("4", "gender"),
    ("5", "caste"),
    ("6", "father_name"),
    ("7", "mother_name"),
    ("8", "guardian_name"),
    ("9", "address_for_correspondence"),
    ("10", "contact_no"),
    ("11", "emergency_contact_no"),
    ("12", "blood_group"),
    ("13", "email_id"),
    ("14", "identification_mark"),
    ("15", "name_of_course"),
    ("16", "name_of_college"),
    ("17", "academic_session"),
]

SSUHS_CANONICAL_KEYS = {
    "name_of_student": "name",
    "address_for_correspondence": "address",
    "contact_no": "phone",
}

NOISE_PATTERNS = (
    "affix passport",
    "size coloured",
    "size colored",
    "photo",
    "full signature of guardian with date",
    "full signature of candidate with date",
    "(in capital letters)",
)


async def process_document(file_path: str) -> dict:
    """
    Extract structured fields from a document.

    For SSUHS admission and identity-card forms we apply a format-aware parser.
    For other documents we keep a generic key/value fallback.
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

    try:
        chunks: list[str] = []

        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text(layout=True) or page.extract_text() or ""

                if page_text:
                    chunks.append(page_text)

        return "\n".join(chunks)

    except Exception:
        raise RuntimeError(f"Failed to extract text from PDF: {path.name}")


def _extract_image_text(path: Path) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "Image OCR requires the optional 'pytesseract' and 'Pillow' dependencies."
        ) from exc

    try:
        with Image.open(path) as image:
            return pytesseract.image_to_string(image)

    except Exception:
        raise RuntimeError(f"Failed to extract text from image: {path.name}")


def _parse_template_fields(text: str) -> dict:
    cleaned_text = _normalize_text(text)

    if _looks_like_ssuhs_form(cleaned_text):
        parsed = _parse_ssuhs_form(cleaned_text)
        if parsed:
            return parsed

    return _parse_generic_key_values(cleaned_text)


def _looks_like_ssuhs_form(text: str) -> bool:
    lowered = text.lower()
    return (
        "srimanta sankaradeva university of health sciences" in lowered
        and (
            "admission form" in lowered
            or "form for identity card" in lowered
        )
    )


def _parse_ssuhs_form(text: str) -> dict:
    sections: list[tuple[str, list[tuple[str, str]]]] = []

    admission = _slice_section(text, "ADMISSION FORM")
    if admission:
        sections.append(("admission_form", SSUHS_FIELD_PATTERNS))

    identity = _slice_section(text, "FORM FOR IDENTITY CARD")
    if identity:
        sections.append(("identity_card_form", SSUHS_IDENTITY_FIELD_PATTERNS))

    if not sections:
        if "form for identity card" in text.lower():
            sections.append(("identity_card_form", SSUHS_IDENTITY_FIELD_PATTERNS))
            identity = text
            admission = ""
        else:
            sections.append(("admission_form", SSUHS_FIELD_PATTERNS))
            admission = text
            identity = ""

    parsed: dict[str, str] = {}

    for section_name, fields in sections:
        section_text = admission if section_name == "admission_form" else identity
        section_data = _extract_numbered_fields(section_text, fields)
        for key, value in section_data.items():
            parsed[key] = value

        if section_data:
            parsed["_template"] = section_name

    _add_canonical_fields(parsed)
    return parsed


def _slice_section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start == -1:
        return ""

    remainder = text[start:]
    next_breaks = [
        idx for idx in (
            remainder.find("\f"),
            remainder.find("ADMISSION FORM", len(heading)),
            remainder.find("FORM FOR IDENTITY CARD", len(heading)),
        )
        if idx > 0
    ]
    end = min(next_breaks) if next_breaks else len(remainder)
    return remainder[:end]


def _extract_numbered_fields(
    section_text: str,
    field_patterns: list[tuple[str, str]],
) -> dict[str, str]:
    results: dict[str, str] = {}

    for index, (_, field_name) in enumerate(field_patterns):
        number, _ = field_patterns[index]
        next_number = field_patterns[index + 1][0] if index + 1 < len(field_patterns) else None
        value = _extract_field_block(section_text, number, next_number)
        cleaned = _clean_value(value)
        if cleaned:
            results[field_name] = cleaned

    return results


def _extract_field_block(section_text: str, number: str, next_number: str | None) -> str:
    start_pattern = re.compile(rf"(?:^|\n)\s*{re.escape(number)}\.\s*", re.MULTILINE)
    start_match = start_pattern.search(section_text)
    if not start_match:
        return ""

    start = start_match.end()
    if next_number:
        end_pattern = re.compile(rf"(?:^|\n)\s*{re.escape(next_number)}\.\s*", re.MULTILINE)
        end_match = end_pattern.search(section_text, start)
        end = end_match.start() if end_match else len(section_text)
    else:
        end = len(section_text)

    block = section_text[start:end]
    block = re.sub(r"^[^:]*:\s*", "", block, count=1, flags=re.DOTALL)
    return block


def _clean_value(value: str) -> str:
    if not value:
        return ""

    cleaned = value.replace("\f", " ")
    cleaned = cleaned.replace("…", ".")
    cleaned = cleaned.replace("’", "'")
    cleaned = cleaned.replace("“", '"').replace("”", '"')
    cleaned = re.sub(r"[._]{4,}", " ", cleaned)
    cleaned = re.sub(r"\.{3,}", " ", cleaned)
    cleaned = re.sub(r"[ ]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n+", "\n", cleaned)
    cleaned = cleaned.strip(" .:\n\t")

    lines = []
    for line in cleaned.splitlines():
        normalized = re.sub(r"\s+", " ", line).strip(" .:\t")
        if normalized and normalized.lower() not in NOISE_PATTERNS:
            lines.append(normalized)

    if not lines:
        return ""

    value = " ".join(lines)
    value = re.sub(r"\s{2,}", " ", value).strip()
    value = re.sub(r"^\(in capital letters\)\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*\(in capital letters\)$", "", value, flags=re.IGNORECASE)
    for noise in NOISE_PATTERNS:
        value = re.sub(re.escape(noise), " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s{2,}", " ", value).strip()

    if re.fullmatch(r"[-./: ]*", value):
        return ""

    return value


def _add_canonical_fields(data: dict[str, str]) -> None:
    for source_key, canonical_key in SSUHS_CANONICAL_KEYS.items():
        if source_key in data and canonical_key not in data:
            data[canonical_key] = data[source_key]


def _normalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("’", "'")
    normalized = normalized.replace("“", '"').replace("”", '"')
    normalized = normalized.replace("–", "-").replace("—", "-")
    normalized = normalized.replace("Cast", "Caste")
    normalized = re.sub(r"Father\s*s\s*Name", "Father's Name", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"Mother\s*s\s*Name", "Mother's Name", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"Guardian\s*s\s*Name", "Guardian's Name", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"E[\s-]*mail\s*id", "E-mail id", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\u00a0", " ", normalized)
    return normalized


def _parse_generic_key_values(text: str) -> dict:
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
    return FIELD_ALIASES.get(
        normalized,
        re.sub(r"[^a-z0-9_]+", "_", normalized).strip("_"),
    )
