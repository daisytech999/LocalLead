"""Opportunity scoring: turn audit flags + business signals into a 0-100 score.

Higher score = bigger opportunity for a freelancer (more problems to fix on a
business that's otherwise active enough to be worth pitching).
"""

# Weight per failed audit signal. "No website" is the biggest opportunity.
WEIGHTS = {
    "no_website": 55,
    "broken_site": 45,
    "no_ssl": 18,
    "not_mobile": 16,
    "slow_load": 12,
    "no_schema": 8,
    "weak_meta": 8,
    "no_maps_embed": 6,
    "no_click_to_call": 6,
    "low_reviews": 10,
}


def score_lead(flags: list[dict], review_count: int | None, rating: float | None) -> int:
    failed = {f["key"] for f in flags if f.get("failed")}
    raw = sum(WEIGHTS.get(k, 0) for k in failed)

    # Checks are gated by reachability, so only certain flags can co-occur.
    # Normalize against the achievable max for the lead's path, otherwise the
    # strongest signals (no site / broken site) look artificially weak.
    if "no_website" in failed:
        denom = WEIGHTS["no_website"] + WEIGHTS["low_reviews"]
    elif "broken_site" in failed:
        denom = WEIGHTS["broken_site"] + WEIGHTS["no_ssl"] + WEIGHTS["low_reviews"]
    else:
        denom = sum(v for k, v in WEIGHTS.items() if k not in ("no_website", "broken_site"))
    base = min(100, round(raw / denom * 100))

    # Activity bump: a business with reviews is reachable/worth pitching, so a
    # broken/absent site there is a hotter lead than a dead listing.
    if review_count:
        if review_count >= 50:
            base = min(100, base + 8)
        elif review_count >= 20:
            base = min(100, base + 5)
        elif review_count >= 5:
            base = min(100, base + 2)

    # A high rating with bad web presence = motivated, quality owner = hotter.
    if rating and rating >= 4.3 and any(f.get("failed") for f in flags):
        base = min(100, base + 3)

    return base


def hotness(score: int | None) -> str:
    if score is None:
        return "unknown"
    if score >= 80:
        return "hot"
    if score >= 60:
        return "warm"
    return "cold"
