"""Outgoing email. Development: written to the log and data/outbox/*.eml. Production: SMTP."""
import logging
import smtplib
import time
from email.message import EmailMessage

from ..config import (DATA_DIR, EMAIL_BACKEND, EMAIL_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_TLS,
                      SMTP_USER)

log = logging.getLogger("plantdoctor.email")
OUTBOX = DATA_DIR / "outbox"


def send(to: str, subject: str, text: str):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = EMAIL_FROM, to, subject
    msg.set_content(text)
    if EMAIL_BACKEND == "smtp":
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
            if SMTP_TLS:
                s.starttls()
            if SMTP_USER:
                s.login(SMTP_USER, SMTP_PASSWORD)
            s.send_message(msg)
        log.info("email sent to %s: %s", to, subject)
        return
    OUTBOX.mkdir(parents=True, exist_ok=True)
    path = OUTBOX / f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 10**9:09d}.eml"
    path.write_bytes(bytes(msg))
    log.warning("[dev email] to=%s subject=%r file=%s\n%s", to, subject, path, text)


def verification_email(to: str, name: str, link: str):
    send(to, "Confirm your PlantDoctor email",
         f"Hello {name},\n\nPlease confirm your email address by opening this link (valid for 48 hours):\n\n{link}\n\n"
         "If you did not create a PlantDoctor account you can ignore this message.\n")


def reset_email(to: str, name: str, link: str):
    send(to, "Reset your PlantDoctor password",
         f"Hello {name},\n\nSomeone (hopefully you) asked to reset your PlantDoctor password. "
         f"Open this link within 1 hour to choose a new one:\n\n{link}\n\n"
         "If you did not ask for this, ignore this email — your password will not change.\n")
