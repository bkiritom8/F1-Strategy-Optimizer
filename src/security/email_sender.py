"""Email sender for account verification and OTP emails.

Provider is selected via EMAIL_PROVIDER env var:
  - "sendgrid"  -> SendGrid REST API (SENDGRID_API_KEY required)
  - "smtp"      -> SMTP (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS)

Other env vars:
  EMAIL_FROM     sender address   (default: noreply@f1optimizer.app)
  APP_BASE_URL   app root URL     (default: https://f1optimizer.app)
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

_EMAIL_FROM = os.environ.get("EMAIL_FROM", "noreply@f1optimizer.app")
_APP_BASE_URL = os.environ.get("APP_BASE_URL", "https://f1optimizer.app").rstrip("/")
_EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "smtp").lower()


# ── Verification email templates ──────────────────────────────────────────────


def _html_verify(username: str, verify_url: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px">
  <h2 style="color:#e10600">F1 Strategy Optimizer</h2>
  <p>Hi <strong>{username}</strong>,</p>
  <p>Thanks for registering. Click the button below to verify your email address.</p>
  <p style="margin:32px 0">
    <a href="{verify_url}"
       style="background:#e10600;color:#fff;padding:12px 24px;
              text-decoration:none;border-radius:4px;font-weight:bold">
      Verify Email Address
    </a>
  </p>
  <p style="color:#666;font-size:13px">
    This link expires in 24 hours. If you did not create this account, ignore this email.
  </p>
  <p style="color:#999;font-size:12px">
    Or copy this URL into your browser:<br>{verify_url}
  </p>
</body>
</html>"""


def _plain_verify(username: str, verify_url: str) -> str:
    return (
        f"Hi {username},\n\n"
        "Thanks for registering with F1 Strategy Optimizer.\n\n"
        f"Verify your email address:\n{verify_url}\n\n"
        "This link expires in 24 hours.\n"
        "If you did not create this account, ignore this email."
    )


# ── OTP email templates ───────────────────────────────────────────────────────


def _html_otp(username: str, otp_code: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px">
  <h2 style="color:#e10600">F1 Strategy Optimizer</h2>
  <p>Hi <strong>{username}</strong>,</p>
  <p>Your one-time sign-in code is:</p>
  <div style="margin:32px 0;text-align:center">
    <span style="display:inline-block;background:#111;color:#fff;
                 font-size:36px;font-weight:800;letter-spacing:12px;
                 padding:20px 32px;border-radius:8px;border:2px solid #e10600">
      {otp_code}
    </span>
  </div>
  <p style="color:#666;font-size:13px">
    This code expires in <strong>10 minutes</strong> and can only be used once.
    If you did not request this code, you can safely ignore this email.
  </p>
</body>
</html>"""


def _plain_otp(username: str, otp_code: str) -> str:
    return (
        f"Hi {username},\n\n"
        f"Your one-time sign-in code is: {otp_code}\n\n"
        "This code expires in 10 minutes and can only be used once.\n"
        "If you did not request this, ignore this email."
    )


# ── Public API ────────────────────────────────────────────────────────────────


def send_verification_email(to_email: str, username: str, token: str) -> None:
    """Send an email verification link. Raises on delivery failure."""
    verify_url = f"{_APP_BASE_URL}/verify-email?token={token}"
    if _EMAIL_PROVIDER == "sendgrid":
        _sendgrid(
            to_email,
            subject="Verify your F1 Strategy Optimizer account",
            plain=_plain_verify(username, verify_url),
            html=_html_verify(username, verify_url),
        )
    else:
        _smtp(
            to_email,
            subject="Verify your F1 Strategy Optimizer account",
            plain=_plain_verify(username, verify_url),
            html=_html_verify(username, verify_url),
        )
    logger.info("verification email sent to %s", to_email)


def send_otp_email(to_email: str, username: str, otp_code: str) -> None:
    """
    Send a 6-digit OTP code to the user for passwordless sign-in.
    The code expires in 10 minutes as enforced by UserStore.create_otp().
    """
    if _EMAIL_PROVIDER == "sendgrid":
        _sendgrid(
            to_email,
            subject="Your F1 Optimizer sign-in code",
            plain=_plain_otp(username, otp_code),
            html=_html_otp(username, otp_code),
        )
    else:
        _smtp(
            to_email,
            subject="Your F1 Optimizer sign-in code",
            plain=_plain_otp(username, otp_code),
            html=_html_otp(username, otp_code),
        )
    logger.info("OTP email sent to %s", to_email)


# ── SendGrid ──────────────────────────────────────────────────────────────────


def _sendgrid(to_email: str, subject: str, plain: str, html: str) -> None:
    """Send via SendGrid REST API. Requires SENDGRID_API_KEY env var."""
    import httpx

    api_key = os.environ.get("SENDGRID_API_KEY")
    if not api_key:
        raise RuntimeError("SENDGRID_API_KEY env var is not set")

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": _EMAIL_FROM, "name": "F1 Strategy Optimizer"},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": plain},
            {"type": "text/html", "value": html},
        ],
    }

    resp = httpx.post(
        "https://api.sendgrid.com/v3/mail/send",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=10.0,
    )
    resp.raise_for_status()


# ── SMTP ──────────────────────────────────────────────────────────────────────


def _smtp(to_email: str, subject: str, plain: str, html: str) -> None:
    """Send via SMTP. Uses SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS env vars."""
    host = os.environ.get("SMTP_HOST", "localhost")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASS", "")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = _EMAIL_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    if port == 465:
        with smtplib.SMTP_SSL(host, port) as smtp:
            if user:
                smtp.login(user, password)
            smtp.sendmail(_EMAIL_FROM, [to_email], msg.as_string())
    else:
        with smtplib.SMTP(host, port) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            if user:
                smtp.login(user, password)
            smtp.sendmail(_EMAIL_FROM, [to_email], msg.as_string())
