import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import LEAD_STATUSES, Lead, User
from ..schemas import LeadOut, LeadUpdate, SearchRequest, SearchResponse
from ..services import places
from ..services.audit import audit_website
from ..services.report import build_report
from ..services.scoring import score_lead
from ..usage import can_search, record_search, search_limit

router = APIRouter(prefix="/api", tags=["leads"])


def _audit_and_score(biz: dict) -> dict:
    flags, meta = audit_website(biz.get("website"), biz.get("review_count"))
    biz["audit"] = flags
    biz["score"] = score_lead(flags, biz.get("review_count"), biz.get("rating"))
    biz["contacts"] = meta.get("contacts", {"email": None, "socials": []})
    return biz


def _lead_to_out(lead: Lead) -> LeadOut:
    audit = json.loads(lead.audit_json) if lead.audit_json else []
    socials = json.loads(lead.contact_socials) if lead.contact_socials else []
    return LeadOut(
        id=lead.id, place_id=lead.place_id, name=lead.name, address=lead.address,
        phone=lead.phone, website=lead.website, category=lead.category, city=lead.city,
        rating=lead.rating, review_count=lead.review_count, score=lead.score,
        status=lead.status, notes=lead.notes, contact_email=lead.contact_email,
        contact_socials=socials, created_at=lead.created_at, audit=audit,
    )


@router.post("/search", response_model=SearchResponse)
def search(payload: SearchRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not can_search(user, db):
        limit = search_limit(user)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Monthly search limit reached ({limit}). Upgrade to Pro for unlimited searches.",
        )

    try:
        businesses = places.search_businesses(payload.category, payload.city, payload.limit)
    except places.PlacesConfigError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except places.PlacesAPIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    # Run website audits concurrently (network-bound).
    with ThreadPoolExecutor(max_workers=8) as pool:
        businesses = list(pool.map(_audit_and_score, businesses))

    businesses.sort(key=lambda b: b.get("score") or 0, reverse=True)

    # Upsert into the user's saved leads (so they persist to the pipeline).
    out_leads: list[LeadOut] = []
    for biz in businesses:
        lead = None
        if biz.get("place_id"):
            lead = (
                db.query(Lead)
                .filter(Lead.user_id == user.id, Lead.place_id == biz["place_id"])
                .first()
            )
        if lead is None:
            lead = Lead(user_id=user.id, place_id=biz.get("place_id"), status="new")
            db.add(lead)
        lead.name = biz.get("name") or "Unknown"
        lead.address = biz.get("address")
        lead.phone = biz.get("phone")
        lead.website = biz.get("website")
        lead.category = payload.category
        lead.city = payload.city
        lead.lat = biz.get("lat")
        lead.lng = biz.get("lng")
        lead.rating = biz.get("rating")
        lead.review_count = biz.get("review_count")
        lead.audit_json = json.dumps(biz.get("audit", []))
        lead.score = biz.get("score")
        contacts = biz.get("contacts") or {}
        # Don't overwrite a found contact with nothing on a re-scan.
        if contacts.get("email"):
            lead.contact_email = contacts["email"]
        if contacts.get("socials"):
            lead.contact_socials = json.dumps(contacts["socials"])
        db.flush()
        out_leads.append(_lead_to_out(lead))

    record_search(user, db)
    db.commit()

    return SearchResponse(
        query=f"{payload.category} in {payload.city}",
        count=len(out_leads),
        searches_used=user.searches_used,
        search_limit=search_limit(user),
        leads=out_leads,
    )


@router.get("/leads", response_model=list[LeadOut])
def list_leads(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    status_filter: str | None = Query(default=None, alias="status"),
):
    q = db.query(Lead).filter(Lead.user_id == user.id)
    if status_filter:
        q = q.filter(Lead.status == status_filter)
    leads = q.order_by(Lead.score.desc().nullslast(), Lead.created_at.desc()).all()
    return [_lead_to_out(l) for l in leads]


@router.patch("/leads/{lead_id}", response_model=LeadOut)
def update_lead(
    lead_id: int, payload: LeadUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == user.id).first()
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    if payload.status is not None:
        if payload.status not in LEAD_STATUSES:
            raise HTTPException(status_code=422, detail=f"status must be one of {LEAD_STATUSES}")
        lead.status = payload.status
    if payload.notes is not None:
        lead.notes = payload.notes
    db.commit()
    db.refresh(lead)
    return _lead_to_out(lead)


@router.delete("/leads/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lead(lead_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == user.id).first()
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    db.delete(lead)
    db.commit()


@router.get("/leads/{lead_id}/report.pdf")
def lead_report(
    lead_id: int,
    brand: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == user.id).first()
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    # White-label branding is an Agency-plan perk; everyone else gets "LocalLead".
    label = brand.strip() if (brand and user.plan == "agency") else "LocalLead"
    pdf = build_report(lead, brand=label or "LocalLead")
    filename = f"audit-{(lead.name or 'lead').lower().replace(' ', '-')[:40]}.pdf"
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/leads/export.csv")
def export_csv(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    leads = db.query(Lead).filter(Lead.user_id == user.id).order_by(Lead.score.desc().nullslast()).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["name", "score", "status", "phone", "email", "website", "address", "city",
         "rating", "review_count", "issues", "notes"]
    )
    for l in leads:
        audit = json.loads(l.audit_json) if l.audit_json else []
        issues = "; ".join(f["label"] for f in audit if f.get("failed"))
        writer.writerow(
            [l.name, l.score, l.status, l.phone, l.contact_email or "", l.website, l.address, l.city,
             l.rating, l.review_count, issues, l.notes or ""]
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=locallead-leads.csv"},
    )
