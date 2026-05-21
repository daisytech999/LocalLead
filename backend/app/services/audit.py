"""Real website audit engine.

Fetches the lead's website and runs a set of checks that map to the audit
points advertised on the marketing site. Each check returns a flag dict:
{key, label, failed, detail}. Network/markup checks are real; the few that
require paid data (live PageSpeed, GMB completeness, NAP) degrade gracefully.
"""

import re
import ssl
import socket
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

USER_AGENT = "LocalLeadAudit/1.0 (+https://locallead.app)"
TIMEOUT = httpx.Timeout(12.0, connect=6.0)
SLOW_THRESHOLD_S = 3.0


def _flag(key: str, label: str, failed: bool, detail: str | None = None) -> dict:
    return {"key": key, "label": label, "failed": failed, "detail": detail}


def _check_ssl_expiry(hostname: str) -> tuple[bool, str | None]:
    """Return (failed, detail). Failed if cert missing or expired."""
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=6) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
        not_after = cert.get("notAfter")
        if not not_after:
            return True, "No certificate expiry found"
        expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            return True, f"Certificate expired {expires.date()}"
        return False, f"Valid until {expires.date()}"
    except (ssl.SSLError, ssl.CertificateError):
        return True, "Invalid or untrusted certificate"
    except (socket.gaierror, socket.timeout, ConnectionError, OSError):
        return True, "Could not establish HTTPS connection"


def audit_website(website: str | None, review_count: int | None = None) -> tuple[list[dict], dict]:
    """Run the audit. Returns (flags, meta) where meta has timing/status info."""
    flags: list[dict] = []
    meta: dict = {}

    # --- No website at all ---
    if not website or not website.strip():
        flags.append(_flag("no_website", "No Website", True, "Business has no website on file"))
        # Without a site, most site-level checks are moot; surface review signal only.
        _append_review_flags(flags, review_count)
        meta["reachable"] = False
        return flags, meta

    url = website.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    html = ""
    status_code = None
    elapsed = None
    reachable = False
    final_url = url

    try:
        with httpx.Client(
            timeout=TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
            verify=True,
        ) as client:
            resp = client.get(url)
            status_code = resp.status_code
            elapsed = resp.elapsed.total_seconds()
            final_url = str(resp.url)
            reachable = True
            if resp.headers.get("content-type", "").startswith(("text/html", "application/xhtml")):
                html = resp.text or ""
    except httpx.HTTPError:
        reachable = False

    meta.update({"status_code": status_code, "elapsed_s": elapsed, "final_url": final_url, "reachable": reachable})

    # --- Broken site ---
    broken = (not reachable) or (status_code is not None and status_code >= 400)
    flags.append(
        _flag(
            "broken_site",
            "Broken Site",
            broken,
            (f"HTTP {status_code}" if status_code and status_code >= 400 else None)
            if reachable
            else "Unreachable / DNS failure",
        )
    )

    # --- SSL ---
    if hostname:
        ssl_failed, ssl_detail = _check_ssl_expiry(hostname)
    else:
        ssl_failed, ssl_detail = True, "No hostname"
    if not final_url.startswith("https://"):
        ssl_failed, ssl_detail = True, "Site does not serve HTTPS"
    flags.append(_flag("no_ssl", "No SSL", ssl_failed, ssl_detail))

    lowered = html.lower()

    # --- Mobile friendly (viewport meta) ---
    has_viewport = bool(re.search(r'<meta[^>]+name=["\']viewport["\']', lowered))
    flags.append(
        _flag("not_mobile", "Not Mobile Friendly", reachable and not has_viewport,
              None if has_viewport else "No responsive viewport meta tag")
    )

    # --- Slow load ---
    slow = bool(elapsed and elapsed > SLOW_THRESHOLD_S)
    flags.append(
        _flag("slow_load", "Slow Load Time", slow,
              f"{elapsed:.1f}s to first response" if elapsed else None)
    )

    # --- Schema markup (LocalBusiness JSON-LD) ---
    has_schema = ("application/ld+json" in lowered) and ("localbusiness" in lowered or "schema.org" in lowered)
    flags.append(
        _flag("no_schema", "No Schema Markup", reachable and not has_schema,
              None if has_schema else "Missing LocalBusiness JSON-LD")
    )

    # --- Weak meta tags ---
    has_title = bool(re.search(r"<title>\s*\S.+?</title>", lowered, re.S))
    has_desc = bool(re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']\s*\S', lowered))
    weak_meta = reachable and not (has_title and has_desc)
    detail = None
    if weak_meta:
        missing = []
        if not has_title:
            missing.append("title")
        if not has_desc:
            missing.append("description")
        detail = "Missing " + ", ".join(missing)
    flags.append(_flag("weak_meta", "Weak Meta Tags", weak_meta, detail))

    # --- Google Maps embed ---
    has_map = ("maps.google" in lowered) or ("google.com/maps" in lowered) or ("maps/embed" in lowered)
    flags.append(
        _flag("no_maps_embed", "No Google Maps Embed", reachable and not has_map,
              None if has_map else "No local map / location embed")
    )

    # --- Click-to-call ---
    has_tel = "tel:" in lowered
    flags.append(
        _flag("no_click_to_call", "No Click-to-Call", reachable and not has_tel,
              None if has_tel else "No tel: link for mobile users")
    )

    _append_review_flags(flags, review_count)
    return flags, meta


def _append_review_flags(flags: list[dict], review_count: int | None) -> None:
    if review_count is None:
        flags.append(_flag("low_reviews", "Low Review Count", False, "Review data unavailable"))
        return
    flags.append(
        _flag("low_reviews", "Low Review Count", review_count < 10, f"{review_count} Google reviews")
    )
