from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, UploadFile, File, Query
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
from app.core.exceptions import NotFoundError, ForbiddenError
from app.api.deps import CurrentUser, require_min_role
from app.services.storage import save_upload
from app.services.extraction import process_document
from app.core.config import settings

router = APIRouter(prefix="/documents", tags=["Documents"])

AdminOrAbove = require_min_role(Role.ADMIN)


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
):
    """Any authenticated user can upload a document."""
    # 1. Persist file to disk
    file_path, size, mime = await save_upload(file, current_user.id)

    # 2. Create DB record (PENDING)
    doc = Document(
        user_id=current_user.id,
        file_path=file_path,
        original_filename=file.filename or "unknown",
        file_size_bytes=size,
        mime_type=mime,
        status=DocStatus.PENDING,
    )
    db.add(doc)
    await db.flush()   # get doc.id

    # 3. Run extraction service
    extracted = await process_document(file_path)

    # 4. Store extracted data
    doc.extracted_data = extracted

    # 5. Audit
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
):
    """
    Users see their own documents.
    Admins see documents belonging to their assigned users (+ their own).
    Super admins see all documents.
    """
    q = select(Document)

    if current_user.role == Role.USER:
        q = q.where(Document.user_id == current_user.id)
    elif current_user.role == Role.ADMIN:
        # Gather IDs of supervised users + self
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
        # Super admin
        if user_id:
            q = q.where(Document.user_id == user_id)

    if status:
        q = q.where(Document.status == status)

    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    result = await db.execute(q.order_by(Document.uploaded_at.desc()).offset((page - 1) * page_size).limit(page_size))
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


# Update (manual correction of extracted data)
@router.put("/{doc_id}", response_model=DocumentResponse)
async def update_document(
    doc_id: int,
    payload: DocumentUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Users can correct their own documents; admins can correct any accessible doc."""
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


# Audit log for a document
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
    # ADMIN: check document owner is supervised by this admin
    result = await db.execute(
        select(User).where(
            (User.id == doc.user_id) &
            ((User.admin_id == current_user.id) | (User.id == current_user.id))
        )
    )
    if not result.scalar_one_or_none():
        raise ForbiddenError("Document does not belong to any user under your supervision.")
