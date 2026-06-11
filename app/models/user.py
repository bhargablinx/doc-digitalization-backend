from datetime import datetime, timezone
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base
from app.core.roles import Role

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.audit_log import AuditLog


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(SAEnum(Role, name="role_enum", values_callable=lambda x: [e.value for e in x]), nullable=False, default=Role.USER)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # user -> admin supervisor
    admin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    supervisor: Mapped[Optional["User"]] = relationship(
        "User", remote_side="User.id", back_populates="supervised_users", foreign_keys=[admin_id]
    )
    supervised_users: Mapped[List["User"]] = relationship(
        "User", back_populates="supervisor", foreign_keys="User.admin_id"
    )
    documents: Mapped[List["Document"]] = relationship(
        "Document", back_populates="uploader", foreign_keys="Document.user_id"
    )
    verified_documents: Mapped[List["Document"]] = relationship(
        "Document", back_populates="verifier", foreign_keys="Document.verified_by"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="actor")

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username} role={self.role}>"
