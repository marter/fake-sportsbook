"""Email verification: issuing links, checking them, and cleaning up unverified accounts."""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from html import escape

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ledger import LedgerEntry
from app.models.user import User
from app.models.verification import EmailVerificationToken
from app.services import email

logger = logging.getLogger(__name__)

RESEND_COOLDOWN = timedelta(minutes=1)
MAX_EMAILS_PER_DAY = 5


class VerificationError(Exception):
    pass


class TooManyEmails(Exception):
    pass


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def is_verified(user: User) -> bool:
    """True if this user may bet: verified, or verification is switched off."""
    return user.email_verified or not get_settings().email_verification_required


def check_rate_limit(db: Session, user: User, now: datetime) -> None:
    def sent_since(since: datetime) -> int:
        return (
            db.scalar(
                select(func.count())
                .select_from(EmailVerificationToken)
                .where(
                    EmailVerificationToken.user_id == user.id,
                    EmailVerificationToken.issued_at > since,
                )
            )
            or 0
        )

    if sent_since(now - RESEND_COOLDOWN):
        raise TooManyEmails("Please wait a minute before requesting another email.")
    if sent_since(now - timedelta(days=1)) >= MAX_EMAILS_PER_DAY:
        raise TooManyEmails("Too many verification emails today. Try again tomorrow.")


def _ttl() -> timedelta:
    return timedelta(hours=get_settings().verification_token_ttl_hours)


def send_verification(db: Session, user: User) -> None:
    """Creates a fresh link and emails it. Caller commits. Sending failures are logged, not
    raised, so a mail outage never blocks sign-up (the user can resend later)."""
    settings = get_settings()
    now = datetime.now(UTC)
    token = secrets.token_urlsafe(32)
    db.add(
        EmailVerificationToken(
            user_id=user.id, token_hash=_hash(token), issued_at=now, expires_at=now + _ttl()
        )
    )
    link = f"{settings.app_base_url.rstrip('/')}/verify-email?token={token}"
    hours = settings.verification_token_ttl_hours
    name = escape(user.display_name)
    try:
        email.send(
            email.Email(
                to=user.email,
                subject="Confirm your email for Fake Sportsbook",
                text=(
                    f"Hi {user.display_name},\n\n"
                    f"Confirm your email to start betting:\n{link}\n\n"
                    f"The link expires in {hours} hours. If you didn't sign up, ignore this."
                ),
                html=(
                    f"<p>Hi {name},</p>"
                    f'<p><a href="{escape(link)}">Confirm your email</a> to start betting.</p>'
                    f"<p>The link expires in {hours} hours. "
                    "If you didn't sign up, you can ignore this email.</p>"
                ),
            )
        )
    except email.EmailError:
        logger.exception("Couldn't send verification email to user %s", user.id)


def verify(db: Session, token: str) -> User:
    """Marks the token's user verified. Raises VerificationError if the link is bad."""
    now = datetime.now(UTC)
    record = db.scalars(
        select(EmailVerificationToken)
        .where(EmailVerificationToken.token_hash == _hash(token))
        .with_for_update()
    ).first()
    if record is None:
        raise VerificationError("That link isn't valid.")
    user = db.get(User, record.user_id)
    assert user is not None
    if user.email_verified:
        return user  # clicking an old link again is harmless
    if record.used_at is not None or record.expires_at <= now:
        raise VerificationError("That link has expired. Request a new one from the app.")

    record.used_at = now
    user.email_verified_at = now
    db.commit()
    return user


def purge_stale_unverified(db: Session) -> int:
    """Deletes accounts that never verified within the allowed window, freeing their slot."""
    settings = get_settings()
    if not settings.email_verification_required:
        return 0
    cutoff = func.now() - timedelta(hours=settings.unverified_account_ttl_hours)
    stale = select(User.id).where(User.email_verified_at.is_(None), User.created_at < cutoff)
    ids = list(db.scalars(stale).all())
    if not ids:
        return 0
    # Unverified users can't bet, so their only other rows are the signup-bonus ledger entry
    # and verification tokens (which cascade).
    db.execute(delete(LedgerEntry).where(LedgerEntry.user_id.in_(ids)))
    db.execute(delete(User).where(User.id.in_(ids)))
    db.commit()
    logger.info("Deleted %d unverified account(s)", len(ids))
    return len(ids)
