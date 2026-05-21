"""Google Places integration for lead discovery.

Uses the Places API (New) Text Search to find businesses by category + city,
then fetches per-place details (website, phone) needed for the audit.
Requires GOOGLE_PLACES_API_KEY. Raises PlacesConfigError if unset so the
router can return a clear 503.
"""

import httpx

from ..config import get_settings

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

SEARCH_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.location,places.rating,places.userRatingCount,"
    "places.websiteUri,places.nationalPhoneNumber,places.primaryType"
)


class PlacesConfigError(RuntimeError):
    pass


class PlacesAPIError(RuntimeError):
    pass


def _api_key() -> str:
    key = get_settings().google_places_api_key
    if not key:
        raise PlacesConfigError("GOOGLE_PLACES_API_KEY is not configured")
    return key


def search_businesses(category: str, city: str, limit: int = 20) -> list[dict]:
    """Return a list of normalized business dicts."""
    key = _api_key()
    query = f"{category} in {city}"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": SEARCH_FIELD_MASK,
    }
    body = {"textQuery": query, "pageSize": min(limit, 20)}

    results: list[dict] = []
    page_token = None
    try:
        with httpx.Client(timeout=20.0) as client:
            while len(results) < limit:
                payload = dict(body)
                if page_token:
                    payload["pageToken"] = page_token
                resp = client.post(TEXT_SEARCH_URL, json=payload, headers=headers)
                if resp.status_code != 200:
                    raise PlacesAPIError(f"Places API error {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                for p in data.get("places", []):
                    results.append(_normalize(p))
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
    except httpx.HTTPError as exc:
        raise PlacesAPIError(f"Network error contacting Places API: {exc}") from exc

    return results[:limit]


def _normalize(p: dict) -> dict:
    loc = p.get("location", {}) or {}
    return {
        "place_id": p.get("id"),
        "name": (p.get("displayName") or {}).get("text"),
        "address": p.get("formattedAddress"),
        "phone": p.get("nationalPhoneNumber"),
        "website": p.get("websiteUri"),
        "category": p.get("primaryType"),
        "lat": loc.get("latitude"),
        "lng": loc.get("longitude"),
        "rating": p.get("rating"),
        "review_count": p.get("userRatingCount"),
    }
