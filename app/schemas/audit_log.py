from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    document_id: int
    action: str
    performed_by: int
    detail: Optional[str]
    timestamp: datetime
