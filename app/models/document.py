from datetime import datetime, timezone
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, DateTime, ForeignKey, Enum as SAEnum, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.audit_log import AuditLog


class DocumentStatus(str):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


import enum

class DocStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # JSONB column for extracted document fields
    extracted_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    status: Mapped[DocStatus] = mapped_column(
        SAEnum(
            DocStatus,
            name="doc_status_enum",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=DocStatus.PENDING,
        index=True,
    )

    verified_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verification_remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    uploader: Mapped["User"] = relationship("User", back_populates="documents", foreign_keys=[user_id])
    verifier: Mapped[Optional["User"]] = relationship("User", back_populates="verified_documents", foreign_keys=[verified_by])
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Document id={self.id} status={self.status} user_id={self.user_id}>"
