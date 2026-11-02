"""Emails to admins about things happening on the site."""

import logging
from dataclasses import dataclass
from html import escape

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User
from app.services import email

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SignupNotice:
    """Plain data, so it can be sent after the request (and its database session) is over."""

    admin_emails: list[str]
    display_name: str
    email: str
    user_count: int
    max_users: int


def signup_notice(db: Session, user: User) -> SignupNotice:
    admins = db.scalars(
        select(User.email).where(User.is_admin, User.is_active, User.id != user.id)
    ).all()
    return SignupNotice(
        admin_emails=list(admins),
        display_name=user.display_name,
        email=user.email,
        user_count=db.scalar(select(func.count()).select_from(User)) or 0,
        max_users=get_settings().max_users,
    )


def send_signup_notice(notice: SignupNotice) -> None:
    """Emails each admin about a new account. Failures are logged: the account exists either
    way, and admins can see it on the admin page."""
    admin_url = f"{get_settings().app_base_url.rstrip('/')}/admin"
    slots_left = max(notice.max_users - notice.user_count, 0)
    slots = (
        "Sign-ups are now closed (the account limit is reached)."
        if slots_left == 0
        else f"{slots_left} sign-up slot{'s' if slots_left != 1 else ''} left."
    )
    name = escape(notice.display_name)
    address = escape(notice.email)
    for to in notice.admin_emails:
        try:
            email.send(
                email.Email(
                    to=to,
                    subject=f"New Fake Sportsbook account: {notice.display_name}",
                    text=(
                        f"{notice.display_name} ({notice.email}) just signed up.\n\n"
                        f"{notice.user_count} of {notice.max_users} accounts. {slots}\n\n"
                        f"Admin page: {admin_url}"
                    ),
                    html=(
                        f"<p><strong>{name}</strong> ({address}) just signed up.</p>"
                        f"<p>{notice.user_count} of {notice.max_users} accounts. {slots}</p>"
                        f'<p><a href="{escape(admin_url)}">Open the admin page</a></p>'
                    ),
                )
            )
        except email.EmailError:
            logger.exception("Couldn't send the new-account email to an admin")
