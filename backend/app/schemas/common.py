from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationMeta(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=25, ge=1, le=100)
    total_items: int = Field(default=0, ge=0)
    total_pages: int = Field(default=0, ge=0)


class MetaInfo(BaseModel):
    request_id: Optional[str] = None
    timestamp: str
    pagination: Optional[PaginationMeta] = None


class StandardResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T
    meta: Optional[MetaInfo] = None


class ErrorDetail(BaseModel):
    field: Optional[str] = None
    issue: str


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: Optional[List[ErrorDetail]] = None
    request_id: Optional[str] = None


class StandardErrorResponse(BaseModel):
    success: bool = False
    error: ErrorInfo
