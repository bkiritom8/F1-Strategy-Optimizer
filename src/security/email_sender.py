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
_APP_BASE_URL = os.environ.get(
    "APP_BASE_URL", "https://f1optimizer.web.app"
).rstrip("/")
_EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "smtp").lower()


# ── Verification email templates ──────────────────────────────────────────────


def _html_verify(username: str, verify_url: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0a0a0a;font-family:'Helvetica Neue',Arial,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0a0a0a">
    <tr><td align="center" style="padding:40px 16px">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#111111;border-radius:16px;border:1px solid #222;overflow:hidden">
        <!-- Header -->
        <tr><td style="padding:32px 40px 24px;border-bottom:1px solid #222">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td>
                <div style="display:inline-block;background:#e10600;width:36px;height:36px;border-radius:10px;text-align:center;line-height:36px;font-weight:900;font-size:18px;color:#fff;font-style:italic">A</div>
              </td>
              <td style="padding-left:12px">
                <span style="color:#ffffff;font-size:18px;font-weight:900;text-transform:uppercase;letter-spacing:-0.5px;font-style:italic">Apex Intelligence</span><br>
                <span style="color:#e10600;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:3px">Race Intelligence</span>
              </td>
            </tr>
          </table>
        </td></tr>
        <!-- Body -->
        <tr><td style="padding:40px">
          <p style="color:#999;font-size:13px;margin:0 0 4px;text-transform:uppercase;letter-spacing:2px;font-weight:700">Account Verification</p>
          <p style="color:#fff;font-size:22px;font-weight:700;margin:0 0 32px">Welcome, {username}</p>
          <p style="color:#aaa;font-size:14px;line-height:1.6;margin:0 0 32px">Thanks for registering with Apex Intelligence. Verify your email address to activate your strategist terminal.</p>
          <!-- CTA Button -->
          <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 32px">
            <tr><td align="center">
              <a href="{verify_url}" style="display:inline-block;background:#e10600;color:#ffffff;font-size:13px;font-weight:800;text-transform:uppercase;letter-spacing:2px;text-decoration:none;padding:16px 40px;border-radius:10px">Verify Email Address</a>
            </td></tr>
          </table>
          <!-- Expiry Badge -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td align="center">
              <div style="display:inline-block;background:rgba(225,6,0,0.1);border:1px solid rgba(225,6,0,0.3);border-radius:8px;padding:10px 20px">
                <span style="color:#e10600;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px">Link expires in 24 hours</span>
              </div>
            </td></tr>
          </table>
        </td></tr>
        <!-- Fallback URL -->
        <tr><td style="padding:0 40px 24px">
          <p style="color:#444;font-size:11px;line-height:1.5;margin:0;word-break:break-all">
            If the button does not work, copy this URL into your browser:<br>
            <span style="color:#666">{verify_url}</span>
          </p>
        </td></tr>
        <!-- Security Footer -->
        <tr><td style="padding:24px 40px;background:#0d0d0d;border-top:1px solid #222">
          <p style="color:#555;font-size:11px;line-height:1.5;margin:0">
            If you did not create this account, no action is needed and this email can be safely ignored.
          </p>
        </td></tr>
        <!-- Brand Footer -->
        <tr><td style="padding:20px 40px;text-align:center">
          <p style="color:#333;font-size:9px;text-transform:uppercase;letter-spacing:3px;font-weight:700;margin:0">&copy; 2026 Apex Strategy Labs</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
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
    digits = "\n".join(
        f'<td style="background:#1a1a1a;color:#ffffff;font-family:monospace;'
        f'font-size:32px;font-weight:800;padding:16px 20px;border-radius:8px;'
        f'text-align:center;border:1px solid #333">{d}</td>'
        for d in otp_code
    )
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0a0a0a;font-family:'Helvetica Neue',Arial,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0a0a0a">
    <tr><td align="center" style="padding:40px 16px">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#111111;border-radius:16px;border:1px solid #222;overflow:hidden">
        <!-- Header -->
        <tr><td style="padding:32px 40px 24px;border-bottom:1px solid #222">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td>
                <div style="display:inline-block;background:#e10600;width:36px;height:36px;border-radius:10px;text-align:center;line-height:36px;font-weight:900;font-size:18px;color:#fff;font-style:italic">A</div>
              </td>
              <td style="padding-left:12px">
                <span style="color:#ffffff;font-size:18px;font-weight:900;text-transform:uppercase;letter-spacing:-0.5px;font-style:italic">Apex Intelligence</span><br>
                <span style="color:#e10600;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:3px">Race Intelligence</span>
              </td>
            </tr>
          </table>
        </td></tr>
        <!-- Body -->
        <tr><td style="padding:40px">
          <p style="color:#999;font-size:13px;margin:0 0 4px;text-transform:uppercase;letter-spacing:2px;font-weight:700">Secure Access Code</p>
          <p style="color:#fff;font-size:22px;font-weight:700;margin:0 0 32px">Hi {username},</p>
          <p style="color:#aaa;font-size:14px;line-height:1.6;margin:0 0 32px">Enter the following code in the Apex Intelligence terminal to authenticate your session.</p>
          <!-- OTP Digits -->
          <table cellpadding="0" cellspacing="8" style="margin:0 auto 32px" role="presentation">
            <tr>
              {digits}
            </tr>
          </table>
          <!-- Expiry Badge -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td align="center">
              <div style="display:inline-block;background:rgba(225,6,0,0.1);border:1px solid rgba(225,6,0,0.3);border-radius:8px;padding:10px 20px">
                <span style="color:#e10600;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px">Expires in 10 minutes &bull; Single use only</span>
              </div>
            </td></tr>
          </table>
        </td></tr>
        <!-- Security Footer -->
        <tr><td style="padding:24px 40px;background:#0d0d0d;border-top:1px solid #222">
          <p style="color:#555;font-size:11px;line-height:1.5;margin:0">
            If you did not request this code, no action is needed. Never share this code with anyone.
          </p>
        </td></tr>
        <!-- Brand Footer -->
        <tr><td style="padding:20px 40px;text-align:center">
          <p style="color:#333;font-size:9px;text-transform:uppercase;letter-spacing:3px;font-weight:700;margin:0">&copy; 2026 Apex Strategy Labs</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
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
