"""Plan usage tracking: monthly search limits and period resets."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .models import PLANS, User

PERIOD_DAYS = 30


def _ensure_period(user: User) -> None:
    """Reset the usage counter if the 30-day billing period has rolled over."""
    start = user.period_start
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - start >= timedelta(days=PERIOD_DAYS):
        user.searches_used = 0
        user.period_start = datetime.now(timezone.utc)


def search_limit(user: User) -> int | None:
    return PLANS.get(user.plan, PLANS["starter"])["monthly_search_limit"]


def can_search(user: User, db: Session) -> bool:
    _ensure_period(user)
    db.commit()
    limit = search_limit(user)
    if limit is None:
        return True
    return user.searches_used < limit


def record_search(user: User, db: Session) -> None:
    user.searches_used += 1
    db.commit()
