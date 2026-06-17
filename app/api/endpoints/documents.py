from datetime import datetime, timezone, date, time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, File, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.session import get_db
from app.models.document import Document, DocStatus
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.document import (
    DocumentResponse, DocumentUpdate,
    VerifyRequest, RejectRequest, DocumentListResponse,
)
from app.core.roles import Role
from app.core.exceptions import NotFoundError, ForbiddenError, AppException, ValidationError
from app.api.deps import CurrentUser, require_min_role
from app.services.storage import save_upload
from app.services.extraction import process_document
from app.core.config import settings

router = APIRouter(prefix="/documents", tags=["Documents"])

AdminOrAbove = require_min_role(Role.ADMIN)


# Upload
@router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
):
    """Any authenticated user can upload a document."""
    file_path, size, mime = await save_upload(file, current_user.id)

    doc = Document(
        user_id=current_user.id,
        file_path=file_path,
        original_filename=file.filename or "unknown",
        file_size_bytes=size,
        mime_type=mime,
        status=DocStatus.PENDING,
    )
    db.add(doc)
    await db.flush()

    extracted = await process_document(file_path)
    doc.extracted_data = extracted

    db.add(AuditLog(
        document_id=doc.id,
        action="uploaded",
        performed_by=current_user.id,
        detail=f"File: {file.filename}",
    ))

    await db.flush()
    await db.refresh(doc)
    return doc


# List documents
@router.get("", response_model=DocumentListResponse)
async def list_documents(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    status: DocStatus | None = None,
    user_id: int | None = None,
    date_from: date | None = Query(None, description="Only return documents uploaded on/after this date (YYYY-MM-DD). Admin/Super Admin only."),
    date_to: date | None = Query(None, description="Only return documents uploaded on/before this date (YYYY-MM-DD). Admin/Super Admin only."),
):
    if (date_from or date_to) and current_user.role == Role.USER:
        raise ForbiddenError("Date range filtering is restricted to admins.")

    if date_from and date_to and date_from > date_to:
        raise ValidationError("date_from cannot be after date_to.")

    q = select(Document)

    if current_user.role == Role.USER:
        q = q.where(Document.user_id == current_user.id)
    elif current_user.role == Role.ADMIN:
        result = await db.execute(
            select(User.id).where((User.admin_id == current_user.id) | (User.id == current_user.id))
        )
        managed_ids = [row[0] for row in result.all()]
        q = q.where(Document.user_id.in_(managed_ids))
        if user_id:
            if user_id not in managed_ids:
                raise ForbiddenError("You can only view documents of users assigned to you.")
            q = q.where(Document.user_id == user_id)
    else:
        if user_id:
            q = q.where(Document.user_id == user_id)

    if status:
        q = q.where(Document.status == status)

    if date_from:
        q = q.where(Document.uploaded_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        q = q.where(Document.uploaded_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))

    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    result = await db.execute(
        q.order_by(Document.uploaded_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    docs = result.scalars().all()

    return DocumentListResponse(total=total or 0, page=page, page_size=page_size, items=list(docs))


# Get single document
@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    doc = await _fetch_doc_or_404(doc_id, db)
    await _assert_doc_access(current_user, doc, db)
    return doc


# FILE SERVING  ← NEW
@router.get("/{doc_id}/file", summary="Stream the original uploaded file")
async def serve_document_file(
    doc_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    download: bool = Query(False, description="Set to true to force a file download instead of inline preview"),
):
    """
    Stream the raw file stored on disk back to the client.

    - **Inline** (default): browser renders PDF/images directly — ideal for preview iframes.
    - **Download** (`?download=true`): forces `Content-Disposition: attachment`.

    Access rules are identical to GET /documents/{id}:
    - Users can only access their own documents.
    - Admins can access documents of users they supervise.
    - Super admins can access any document.
    """
    doc = await _fetch_doc_or_404(doc_id, db)
    await _assert_doc_access(current_user, doc, db)

    file_path = Path(doc.file_path)

    if not file_path.exists():
        raise AppException(
            status_code=404,
            detail=f"Physical file not found on server. It may have been moved or deleted.",
        )

    # Determine content-type — fall back to stored mime or octet-stream
    mime = doc.mime_type or _ext_to_mime(file_path.suffix.lstrip(".").lower())

    disposition = (
        f'attachment; filename="{doc.original_filename}"'
        if download
        else f'inline; filename="{doc.original_filename}"'
    )

    return FileResponse(
        path=str(file_path),
        media_type=mime,
        headers={
            "Content-Disposition": disposition,
            # Allow browser to cache for 5 minutes (file never changes)
            "Cache-Control": "private, max-age=300",
        },
    )


# Update (manual correction of extracted data)
@router.put("/{doc_id}", response_model=DocumentResponse)
async def update_document(
    doc_id: int,
    payload: DocumentUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    doc = await _fetch_doc_or_404(doc_id, db)
    await _assert_doc_access(current_user, doc, db)

    if doc.status == DocStatus.VERIFIED:
        raise ForbiddenError("Cannot edit a verified document.")

    doc.extracted_data = payload.extracted_data
    db.add(AuditLog(
        document_id=doc.id,
        action="data_corrected",
        performed_by=current_user.id,
        detail="Manual correction of extracted data.",
    ))

    await db.flush()
    await db.refresh(doc)
    return doc


# Verify
@router.post("/{doc_id}/verify", response_model=DocumentResponse)
async def verify_document(
    doc_id: int,
    payload: VerifyRequest,
    current_user: CurrentUser,
    _: Annotated[User, AdminOrAbove],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    doc = await _fetch_doc_or_404(doc_id, db)
    await _assert_doc_access(current_user, doc, db)

    doc.status = DocStatus.VERIFIED
    doc.verified_by = current_user.id
    doc.verified_at = datetime.now(timezone.utc)
    doc.verification_remark = payload.remark

    db.add(AuditLog(
        document_id=doc.id,
        action="verified",
        performed_by=current_user.id,
        detail=payload.remark,
    ))

    await db.flush()
    await db.refresh(doc)
    return doc


# Reject
@router.post("/{doc_id}/reject", response_model=DocumentResponse)
async def reject_document(
    doc_id: int,
    payload: RejectRequest,
    current_user: CurrentUser,
    _: Annotated[User, AdminOrAbove],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    doc = await _fetch_doc_or_404(doc_id, db)
    await _assert_doc_access(current_user, doc, db)

    doc.status = DocStatus.REJECTED
    doc.verified_by = current_user.id
    doc.verified_at = datetime.now(timezone.utc)
    doc.verification_remark = payload.remark

    db.add(AuditLog(
        document_id=doc.id,
        action="rejected",
        performed_by=current_user.id,
        detail=payload.remark,
    ))

    await db.flush()
    await db.refresh(doc)
    return doc


# Audit log
@router.get("/{doc_id}/audit", response_model=list)
async def get_audit_log(
    doc_id: int,
    current_user: CurrentUser,
    _: Annotated[User, AdminOrAbove],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    doc = await _fetch_doc_or_404(doc_id, db)
    await _assert_doc_access(current_user, doc, db)

    result = await db.execute(
        select(AuditLog).where(AuditLog.document_id == doc_id).order_by(AuditLog.timestamp)
    )
    return result.scalars().all()


# Helpers
async def _fetch_doc_or_404(doc_id: int, db: AsyncSession) -> Document:
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document")
    return doc


async def _assert_doc_access(current_user: User, doc: Document, db: AsyncSession) -> None:
    if current_user.role == Role.SUPER_ADMIN:
        return
    if current_user.role == Role.USER:
        if doc.user_id != current_user.id:
            raise ForbiddenError()
        return
    result = await db.execute(
        select(User).where(
            (User.id == doc.user_id) &
            ((User.admin_id == current_user.id) | (User.id == current_user.id))
        )
    )
    if not result.scalar_one_or_none():
        raise ForbiddenError("Document does not belong to any user under your supervision.")


def _ext_to_mime(ext: str) -> str:
    return {
        "pdf":  "application/pdf",
        "png":  "image/png",
        "jpg":  "image/jpeg",
        "jpeg": "image/jpeg",
        "tiff": "image/tiff",
        "bmp":  "image/bmp",
    }.get(ext, "application/octet-stream")