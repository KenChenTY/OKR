"""Create local development logins and write generated passwords to an ignored local file."""
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select  # noqa: E402
from app.cli import seed_development  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import session_factory  # noqa: E402
from app.models import User, LocalCredential  # noqa: E402
from app.passwords import hash_password  # noqa: E402


def main():
    if settings().env != "development":
        raise SystemExit("Development only")
    with session_factory()() as db:
        empty = db.scalar(select(User.id).limit(1)) is None
    if empty:
        seed_development()
    path = Path(__file__).resolve().parents[2] / "var" / "development-accounts.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    with session_factory()() as db, db.begin():
        for user in db.scalars(select(User).where(User.subject.like("dev:%"))):
            if db.get(LocalCredential, user.id):
                continue
            username = user.subject.removeprefix("dev:")
            password = secrets.token_urlsafe(20)
            db.add(LocalCredential(user_id=user.id, username=username, password_hash=hash_password(password)))
            records.append(f"{username}\t{password}\t{user.name}\t{user.role}\tuser_id={user.id}")
        if records:
            # Exclusive create avoids overwriting previously handed-off credentials.
            with path.open("x", encoding="utf-8") as output:
                output.write("仅限本地开发；密码请勿提交或分享。可使用 app.cli set-password 重置。\n")
                output.write("账号\t密码\t姓名\t角色\t用户编号\n" + "\n".join(records) + "\n")
    print(f"Created {len(records)} development logins. Passwords are in var/development-accounts.txt")


if __name__ == "__main__":
    main()
