from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- Auth ----------
class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: EmailStr
    plan: str
    searches_used: int
    created_at: datetime


# ---------- Leads / search ----------
class SearchRequest(BaseModel):
    category: str = Field(min_length=1, max_length=120, description="e.g. 'plumbers'")
    city: str = Field(min_length=1, max_length=160, description="e.g. 'Orlando, FL' or a zip code")
    limit: int = Field(default=20, ge=1, le=60)


class AuditFlag(BaseModel):
    key: str
    label: str
    failed: bool
    detail: str | None = None


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    place_id: str | None
    name: str
    address: str | None
    phone: str | None
    website: str | None
    category: str | None
    city: str | None
    rating: float | None
    review_count: int | None
    score: int | None
    status: str
    notes: str | None
    contact_email: str | None = None
    contact_socials: list[str] = []
    created_at: datetime
    audit: list[AuditFlag] = []


class SearchResponse(BaseModel):
    query: str
    count: int
    searches_used: int
    search_limit: int | None
    leads: list[LeadOut]


# ---------- Pipeline ----------
class LeadUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None


# ---------- Billing ----------
class CheckoutRequest(BaseModel):
    plan: str = Field(description="'pro' or 'agency'")


class CheckoutResponse(BaseModel):
    checkout_url: str


# ---------- Watches / alerts ----------
class WatchCreate(BaseModel):
    category: str = Field(min_length=1, max_length=120)
    city: str = Field(min_length=1, max_length=160)


class WatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    category: str
    city: str
    last_scanned_at: datetime | None
    created_at: datetime


class ScanResult(BaseModel):
    new_count: int
    total: int
    error: str | None = None
    new_leads: list[LeadOut] = []
