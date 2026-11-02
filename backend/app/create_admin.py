"""Create (or reset) the first platform administrator in a production database - the only account that exists before anyone registers.
Usage:  SPENDOS_ADMIN_PASSWORD=... python -m app.create_admin admin@yourcompany.com "Your Name"
The password is read from the environment or prompted for; it is never printed or stored anywhere else."""
import getpass
import os
import sys

from sqlalchemy import select

from . import models as m
from .core import EMAIL_RE, SessionLocal, hash_password
from .main import ensure_catalogue, init_db


def main():
    if len(sys.argv) < 3 or not EMAIL_RE.match(sys.argv[1]):
        raise SystemExit('usage: python -m app.create_admin <email> "<name>"')
    email, name = sys.argv[1].lower(), sys.argv[2]
    pw = os.environ.get("SPENDOS_ADMIN_PASSWORD") or getpass.getpass("Password (min 12 characters): ")
    if len(pw) < 12:
        raise SystemExit("Password must be at least 12 characters")
    init_db()
    with SessionLocal() as db:
        ensure_catalogue(db)
        u = db.scalar(select(m.User).where(m.User.email == email))
        if u:
            u.password_hash, u.is_platform_admin, u.is_active, u.failed_logins, u.locked_until = hash_password(pw), True, True, 0, None
        else:
            db.add(m.User(email=email, name=name, password_hash=hash_password(pw), is_platform_admin=True))
        db.commit()
    print(f"Platform administrator ready: {email}")


if __name__ == "__main__":
    main()
