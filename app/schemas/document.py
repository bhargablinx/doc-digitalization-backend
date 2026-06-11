from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel
from app.models.document import DocStatus


class ExtractedData(BaseModel):
    """Represents the fixed template fields extracted from a document."""
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    consumer_number: Optional[str] = None
    # Catch-all for any extra fields returned by the extraction service
    model_config = {"extra": "allow"}


class DocumentResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    original_filename: str
    file_size_bytes: Optional[int]
    mime_type: Optional[str]
    extracted_data: Optional[dict[str, Any]]
    status: DocStatus
    verified_by: Optional[int]
    verification_remark: Optional[str]
    verified_at: Optional[datetime]
    uploaded_at: datetime


class DocumentUpdate(BaseModel):
    """Manual correction of extracted data by admin/user."""
    extracted_data: dict[str, Any]


class VerifyRequest(BaseModel):
    remark: Optional[str] = None


class RejectRequest(BaseModel):
    remark: str


class DocumentListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[DocumentResponse]
