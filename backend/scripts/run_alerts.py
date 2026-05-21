"""Scan every saved search and email owners about new leads.

Run on a schedule (cron / systemd timer), e.g. hourly:
    0 * * * * cd /path/to/backend && .venv/bin/python -m scripts.run_alerts

Requires GOOGLE_PLACES_API_KEY; emails require SMTP_* to be configured.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.models import SavedSearch  # noqa: E402
from app.services import alerts, email  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        watches = db.query(SavedSearch).all()
        print(f"Scanning {len(watches)} watch(es). Email configured: {email.is_configured()}")
        for w in watches:
            result = alerts.scan_and_notify(db, w)
            status = result["error"] or f"{result['new_count']} new / {result['total']} total"
            print(f"  watch#{w.id} {w.category} in {w.city}: {status}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
