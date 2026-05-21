"""Plain SMTP email sender for alert notifications.

No-ops gracefully (returns False) when SMTP is not configured, so the alert
scanner can still record new leads in dev without an email provider.
"""

import smtplib
from email.message import EmailMessage

from ..config import get_settings


def is_configured() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.smtp_user and s.smtp_password)


def send_email(to: str, subject: str, body: str) -> bool:
    s = get_settings()
    if not is_configured():
        return False
    msg = EmailMessage()
    msg["From"] = s.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as server:
        if s.smtp_use_tls:
            server.starttls()
        server.login(s.smtp_user, s.smtp_password)
        server.send_message(msg)
    return True
