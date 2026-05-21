"""Shared lead persistence: audit, score, and upsert into a user's pipeline.

Used by both interactive search and the background alert scanner so the two
paths produce identical lead records.
"""

import json
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from .models import Lead
from .services.audit import audit_website
from .services.scoring import score_lead


def audit_and_score(biz: dict) -> dict:
    flags, meta = audit_website(biz.get("website"), biz.get("review_count"))
    biz["audit"] = flags
    biz["score"] = score_lead(flags, biz.get("review_count"), biz.get("rating"))
    biz["contacts"] = meta.get("contacts", {"email": None, "socials": []})
    return biz


def audit_many(businesses: list[dict], max_workers: int = 8) -> list[dict]:
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(audit_and_score, businesses))


def upsert_lead(db: Session, user_id: int, biz: dict, category: str, city: str) -> Lead:
    lead = None
    if biz.get("place_id"):
        lead = (
            db.query(Lead)
            .filter(Lead.user_id == user_id, Lead.place_id == biz["place_id"])
            .first()
        )
    if lead is None:
        lead = Lead(user_id=user_id, place_id=biz.get("place_id"), status="new")
        db.add(lead)
    lead.name = biz.get("name") or "Unknown"
    lead.address = biz.get("address")
    lead.phone = biz.get("phone")
    lead.website = biz.get("website")
    lead.category = category
    lead.city = city
    lead.lat = biz.get("lat")
    lead.lng = biz.get("lng")
    lead.rating = biz.get("rating")
    lead.review_count = biz.get("review_count")
    lead.audit_json = json.dumps(biz.get("audit", []))
    lead.score = biz.get("score")
    contacts = biz.get("contacts") or {}
    if contacts.get("email"):
        lead.contact_email = contacts["email"]
    if contacts.get("socials"):
        lead.contact_socials = json.dumps(contacts["socials"])
    db.flush()
    return lead
