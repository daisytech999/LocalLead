"""New-lead alerts: re-scan a watched city/category and detect new businesses."""

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..leadstore import audit_many, upsert_lead
from ..models import SavedSearch, User
from . import email, places


def scan_watch(db: Session, watch: SavedSearch, limit: int = 20) -> dict:
    """Run one watch. Returns {new: [..lead dicts..], total, error?}."""
    try:
        businesses = places.search_businesses(watch.category, watch.city, limit)
    except (places.PlacesConfigError, places.PlacesAPIError) as exc:
        return {"new": [], "total": 0, "error": str(exc)}

    seen = set(json.loads(watch.seen_place_ids)) if watch.seen_place_ids else set()
    first_run = not watch.seen_place_ids

    current_ids = {b["place_id"] for b in businesses if b.get("place_id")}
    new_businesses = [b for b in businesses if b.get("place_id") and b["place_id"] not in seen]

    # Audit + persist all results (keeps the pipeline fresh), surface only new.
    audited = audit_many(businesses)
    by_id = {b.get("place_id"): b for b in audited}
    for b in audited:
        upsert_lead(db, watch.user_id, b, watch.category, watch.city)

    watch.seen_place_ids = json.dumps(sorted(seen | current_ids))
    watch.last_scanned_at = datetime.now(timezone.utc)
    db.commit()

    # On the first scan we just establish a baseline — nothing is "new" yet.
    new_leads = [] if first_run else [by_id[b["place_id"]] for b in new_businesses]
    return {"new": new_leads, "total": len(businesses), "error": None}


def scan_and_notify(db: Session, watch: SavedSearch) -> dict:
    result = scan_watch(db, watch)
    new = result["new"]
    if new and email.is_configured():
        user = db.get(User, watch.user_id)
        if user:
            email.send_email(user.email, *_compose(watch, new))
    return result


def _compose(watch: SavedSearch, new_leads: list[dict]) -> tuple[str, str]:
    subject = f"{len(new_leads)} new lead(s): {watch.category} in {watch.city}"
    lines = [f"New businesses found for '{watch.category} in {watch.city}':", ""]
    for b in sorted(new_leads, key=lambda x: x.get("score") or 0, reverse=True):
        issues = ", ".join(f["label"] for f in b.get("audit", []) if f.get("failed")) or "no issues"
        lines.append(f"  [{b.get('score')}] {b.get('name')} — {issues}")
    lines += ["", "Log in to LocalLead to pitch them first."]
    return subject, "\n".join(lines)
