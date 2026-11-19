"""Ensure the personal owner account exists with the configured password."""
from __future__ import annotations

import os

from sqlmodel import Session, select

from app.auth import hash_password
from app.config import settings
from app.db import engine, init_db
from app.models import User


def main() -> None:
    init_db()
    email = settings.owner_emails
    if not email:
        print("OWNER_EMAILS is empty — nothing to set up.")
        return
    owner_email = sorted(email)[0]
    password = os.getenv("OWNER_PASSWORD", settings.OWNER_PASSWORD)
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == owner_email)).first()
        if user:
            user.hashed_password = hash_password(password)
            user.is_owner = True
            user.is_active = True
            user.plan = "owner"
            action = "updated"
        else:
            user = User(
                email=owner_email,
                full_name="Owner",
                hashed_password=hash_password(password),
                is_owner=True,
                is_active=True,
                plan="owner",
            )
            action = "created"
        session.add(user)
        session.commit()
    print(f"Owner account {action}: {owner_email}")


if __name__ == "__main__":
    main()
