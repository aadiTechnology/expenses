"""Outgoing email over SMTP. Configure with environment variables (secrets belong in Coolify, never in the repository):
SPENDOS_SMTP_HOST, SPENDOS_SMTP_PORT (default 587), SPENDOS_SMTP_USER, SPENDOS_SMTP_PASSWORD, SPENDOS_SMTP_FROM,
SPENDOS_SMTP_SECURITY = starttls (default) | ssl | none, and SPENDOS_PUBLIC_URL (the web address used inside email links)."""
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

log = logging.getLogger("spendos.mail")


def settings() -> dict:
    return {"host": os.environ.get("SPENDOS_SMTP_HOST", ""), "port": int(os.environ.get("SPENDOS_SMTP_PORT", "587") or 587),
            "user": os.environ.get("SPENDOS_SMTP_USER", ""), "password": os.environ.get("SPENDOS_SMTP_PASSWORD", ""),
            "sender": os.environ.get("SPENDOS_SMTP_FROM", ""), "security": os.environ.get("SPENDOS_SMTP_SECURITY", "starttls").lower()}


def configured() -> bool:
    s = settings()
    return bool(s["host"] and s["sender"])


def public_url() -> str:
    return os.environ.get("SPENDOS_PUBLIC_URL", "http://localhost:8000").rstrip("/")


def send(to: str, subject: str, text: str) -> bool:
    """Returns True when the server accepted the message. Never raises and never logs the body or credentials."""
    s = settings()
    if not configured():
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s["sender"], to, subject
    msg.set_content(text)
    try:
        if s["security"] == "ssl":
            smtp = smtplib.SMTP_SSL(s["host"], s["port"], timeout=15, context=ssl.create_default_context())
        else:
            smtp = smtplib.SMTP(s["host"], s["port"], timeout=15)
        with smtp:
            if s["security"] == "starttls":
                smtp.starttls(context=ssl.create_default_context())
            if s["user"]:
                smtp.login(s["user"], s["password"])
            smtp.send_message(msg)
        return True
    except Exception as e:  # noqa: BLE001 - email trouble must not break the request that triggered it
        log.warning("email to %s failed: %s", to.split("@")[-1], type(e).__name__)
        return False


def reset_email(name: str, token: str) -> tuple[str, str]:
    link = f"{public_url()}/reset?token={token}"
    return "Reset your Aadi SpendOS password", f"Hello {name},\n\nUse this link within 1 hour to choose a new password:\n{link}\n\nIf you did not ask for this, ignore this email; your password stays unchanged.\n"


def invite_email(name: str, org: str, token: str) -> tuple[str, str]:
    link = f"{public_url()}/reset?token={token}"
    return f"You have been invited to {org} on Aadi SpendOS", f"Hello {name},\n\nYou have been invited to {org} on Aadi SpendOS. Choose your password within 7 days using this link:\n{link}\n\nThen sign in at {public_url()}.\n"
