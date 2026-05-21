import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import SavedSearch, User
from ..schemas import LeadOut, ScanResult, WatchCreate, WatchOut
from ..services import alerts

router = APIRouter(prefix="/api/watches", tags=["alerts"])


@router.get("", response_model=list[WatchOut])
def list_watches(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(SavedSearch).filter(SavedSearch.user_id == user.id).order_by(SavedSearch.created_at.desc()).all()


@router.post("", response_model=WatchOut, status_code=status.HTTP_201_CREATED)
def create_watch(payload: WatchCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    existing = (
        db.query(SavedSearch)
        .filter(SavedSearch.user_id == user.id, SavedSearch.category == payload.category, SavedSearch.city == payload.city)
        .first()
    )
    if existing:
        return existing
    watch = SavedSearch(user_id=user.id, category=payload.category.strip(), city=payload.city.strip())
    db.add(watch)
    db.commit()
    db.refresh(watch)
    return watch


@router.delete("/{watch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watch(watch_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    watch = db.query(SavedSearch).filter(SavedSearch.id == watch_id, SavedSearch.user_id == user.id).first()
    if not watch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watch not found")
    db.delete(watch)
    db.commit()


@router.post("/{watch_id}/scan", response_model=ScanResult)
def scan_watch(watch_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    watch = db.query(SavedSearch).filter(SavedSearch.id == watch_id, SavedSearch.user_id == user.id).first()
    if not watch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watch not found")
    result = alerts.scan_and_notify(db, watch)
    new_leads = [
        LeadOut(
            id=0, place_id=b.get("place_id"), name=b.get("name") or "Unknown", address=b.get("address"),
            phone=b.get("phone"), website=b.get("website"), category=watch.category, city=watch.city,
            rating=b.get("rating"), review_count=b.get("review_count"), score=b.get("score"),
            status="new", notes=None,
            contact_email=(b.get("contacts") or {}).get("email"),
            contact_socials=(b.get("contacts") or {}).get("socials", []),
            created_at=watch.created_at,
            audit=b.get("audit", []),
        )
        for b in result["new"]
    ]
    return ScanResult(new_count=len(result["new"]), total=result["total"], error=result["error"], new_leads=new_leads)
