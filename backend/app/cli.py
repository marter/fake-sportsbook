"""Server-side admin commands, e.g.:

    docker compose ... exec backend python -m app.cli make-admin you@example.com
    docker compose ... exec backend python -m app.cli settle
"""

import argparse

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.user import User


def set_admin(email: str, is_admin: bool) -> None:
    with SessionLocal() as db:
        user = db.scalars(select(User).where(User.email == email.lower())).first()
        if user is None:
            raise SystemExit(f"No user with email {email}")
        user.is_admin = is_admin
        db.commit()
        print(f"{user.display_name} <{user.email}> is_admin={is_admin}")


def settle_now() -> None:
    from app.services.settlement import settle_if_due

    with SessionLocal() as db:
        print(f"Settled {settle_if_due(db, force_fetch=True)} bet(s)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("make-admin", "remove-admin"):
        commands.add_parser(name).add_argument("email")
    commands.add_parser("settle", help="Fetch scores now (ignoring the throttle) and settle bets")
    args = parser.parse_args()
    if args.command == "settle":
        settle_now()
    else:
        set_admin(args.email, is_admin=args.command == "make-admin")


if __name__ == "__main__":
    main()
