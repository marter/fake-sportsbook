"""Sends email through the configured backend.

- "console": logs the message (local dev: the verification link shows up in the backend logs)
- "resend": sends through Resend's API (production)
- "memory": appends to `outbox` (tests)
"""

import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class Email:
    to: str
    subject: str
    text: str
    html: str


outbox: list[Email] = []


class EmailError(Exception):
    pass


def send(email: Email) -> None:
    settings = get_settings()
    if settings.email_backend == "memory":
        outbox.append(email)
    elif settings.email_backend == "resend":
        try:
            response = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": settings.email_from,
                    "to": [email.to],
                    "subject": email.subject,
                    "text": email.text,
                    "html": email.html,
                },
                timeout=10,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EmailError(str(exc)) from exc
    else:
        logger.warning("Email to %s: %s\n%s", email.to, email.subject, email.text)
