"""Initial schema — users, documents, audit_logs

Revision ID: 0001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE role_enum AS ENUM ('super_admin', 'admin', 'user')")
    op.execute("CREATE TYPE doc_status_enum AS ENUM ('pending', 'verified', 'rejected')")

    op.execute("""
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(64) NOT NULL UNIQUE,
            email VARCHAR(255) NOT NULL UNIQUE,
            hashed_password VARCHAR(255) NOT NULL,
            role role_enum NOT NULL DEFAULT 'user',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_users_username ON users (username)")
    op.execute("CREATE INDEX ix_users_email ON users (email)")

    op.execute("""
        CREATE TABLE documents (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            file_path VARCHAR(512) NOT NULL,
            original_filename VARCHAR(255) NOT NULL,
            file_size_bytes INTEGER,
            mime_type VARCHAR(128),
            extracted_data JSONB,
            status doc_status_enum NOT NULL DEFAULT 'pending',
            verified_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            verification_remark TEXT,
            verified_at TIMESTAMPTZ,
            uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_documents_user_id ON documents (user_id)")
    op.execute("CREATE INDEX ix_documents_status ON documents (status)")

    op.execute("""
        CREATE TABLE audit_logs (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            action VARCHAR(64) NOT NULL,
            performed_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            detail TEXT,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_audit_logs_document_id ON audit_logs (document_id)")
    op.execute("CREATE INDEX ix_audit_logs_timestamp ON audit_logs (timestamp)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_logs")
    op.execute("DROP TABLE IF EXISTS documents")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TYPE IF EXISTS doc_status_enum")
    op.execute("DROP TYPE IF EXISTS role_enum")