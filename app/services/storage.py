import uuid
from pathlib import Path
from datetime import datetime, timezone
import aiofiles
from fastapi import UploadFile
from app.core.config import settings
from app.core.exceptions import FileTooLargeError, UnsupportedFileTypeError


async def save_upload(file: UploadFile, user_id: int) -> tuple[str, int, str]:
    """
    Persist an uploaded file to the UPLOAD_DIR.

    Returns:
        (relative_file_path, size_in_bytes, mime_type)
    """
    # Validate extension
    original_name = file.filename or "unknown"
    ext = Path(original_name).suffix.lstrip(".").lower()
    if ext not in settings.allowed_extensions_set:
        raise UnsupportedFileTypeError(settings.allowed_extensions_set)

    # Read content
    content = await file.read()
    if len(content) > settings.max_file_size_bytes:
        raise FileTooLargeError(settings.MAX_FILE_SIZE_MB)

    # Build storage path: uploads/<user_id>/<date>/<uuid>.<ext>
    date_part = datetime.now(
        timezone.utc
    ).strftime("%Y/%m/%d")
    dest_dir = Path(settings.UPLOAD_DIR) / str(user_id) / date_part
    dest_dir.mkdir(parents=True, exist_ok=True)

    unique_name = f"{uuid.uuid4().hex}.{ext}"
    dest_path = dest_dir / unique_name

    async with aiofiles.open(dest_path, "wb") as f:
        await f.write(content)

    mime = file.content_type or _ext_to_mime(ext)
    return str(dest_path), len(content), mime


def _ext_to_mime(ext: str) -> str:
    mapping = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "tiff": "image/tiff",
        "bmp": "image/bmp",
    }
    return mapping.get(ext, "application/octet-stream")
