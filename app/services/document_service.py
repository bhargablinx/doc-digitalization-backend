from app.services.pdf_extractor import extract_pdf_text
from app.services.ocr_extractor import extract_image_text

from app.parsers.pdf_parser import parse_pdf_text
from app.parsers.ocr_parser import parse_ocr_text


def process_document(file_path: str, filename: str):

    if filename.endswith(".pdf"):

        text = extract_pdf_text(file_path)

        data = parse_pdf_text(text)

        return data

    elif filename.lower().endswith((".jpg", ".jpeg", ".png")):

        text = extract_image_text(file_path)

        data = parse_ocr_text(text)

        return data

    else:
        raise ValueError("Unsupported file type")