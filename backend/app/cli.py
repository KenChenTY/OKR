"""Explicit initialization commands; the API never seeds or migrates on startup."""

import argparse
from datetime import date

from sqlalchemy import select

from .config import settings
from .db import session_factory
from .models import Cycle, OrgUnit, User


def seed_development():
    if settings().env == "production":
        raise SystemExit("Development seeding is forbidden in production")
    with session_factory()() as db, db.begin():
        if db.scalar(select(User.id).limit(1)):
            raise SystemExit("Users already exist; seed refused")
        division = OrgUnit(name="科技事业部", unit_type="division")
        db.add(division)
        db.flush()
        department = OrgUnit(name="运营技术部", parent_id=division.id, unit_type="department")
        other = OrgUnit(name="数据管理部", parent_id=division.id, unit_type="department")
        db.add_all([department, other])
        db.flush()
        for subject, name, role, org in [
            ("dev:employee", "陈晓 · 目标负责人", "Employee", department.id),
            ("dev:manager", "林悦 · 部门经理", "Manager", department.id),
            ("dev:division", "周宁 · 事业部负责人", "Division Head", division.id),
            ("dev:pmo", "王敏 · PMO", "PMO", division.id),
            ("dev:audit", "赵明 · 审计", "Audit", division.id),
            ("dev:other", "李可 · 其他部门员工", "Employee", other.id),
            ("dev:admin", "系统管理员", "System Admin", division.id),
            ("dev:hr", "人力资源专员", "HR", department.id),
        ]:
            db.add(User(subject=subject, name=name, role=role, org_id=org))
        year = date.today().year
        for q in range(1, 5):
            start = date(year, 3 * q - 2, 1)
            end = date(year, 3 * q + 1, 1) if q < 4 else date(year + 1, 1, 1)
            from datetime import timedelta

            db.add(Cycle(name=f"{year} Q{q}", start_date=start, end_date=end - timedelta(days=1)))
    print("Development organization, users and cycles created. No business records fabricated.")


def provision_user(args):
    allowed = {"Employee", "Manager", "Division Head", "PMO", "HR", "System Admin", "Audit"}
    if args.role not in allowed:
        raise SystemExit("Unknown role")
    with session_factory()() as db, db.begin():
        if not db.get(OrgUnit, args.org_id):
            raise SystemExit("Organization does not exist")
        if db.scalar(select(User.id).where(User.subject == args.subject)):
            raise SystemExit("Identity already provisioned")
        db.add(User(subject=args.subject, name=args.name, role=args.role, org_id=args.org_id))
    print("User provisioned")


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("seed-development")
    password = commands.add_parser("set-password", help="Create or reset an existing user's local login")
    password.add_argument("--user-id", type=int, required=True)
    password.add_argument("--username", required=True)
    org = commands.add_parser("add-org")
    org.add_argument("--name", required=True)
    org.add_argument("--parent-id", type=int)
    org.add_argument("--type", choices=["corporate", "division", "department", "team"], default="department")
    cycle = commands.add_parser("add-cycle")
    cycle.add_argument("--name", required=True)
    cycle.add_argument("--start", type=date.fromisoformat, required=True)
    cycle.add_argument("--end", type=date.fromisoformat, required=True)
    provision = commands.add_parser("provision-user")
    provision.add_argument("--subject", required=True, help="tenant-id:object-id")
    provision.add_argument("--name", required=True)
    provision.add_argument("--role", required=True)
    provision.add_argument("--org-id", type=int, required=True)
    args = parser.parse_args()
    if args.command == "set-password":
        from getpass import getpass
        from sqlalchemy import delete
        from .models import LocalCredential, AppSession, LoginAttempt
        from .passwords import hash_password, normalize_username
        from .security import digest
        from .services import lock
        username = normalize_username(args.username)
        secret = getpass("New password (12–128 characters): ")
        if secret != getpass("Confirm password: "):
            raise SystemExit("Passwords do not match")
        encoded = hash_password(secret)
        with session_factory()() as db, db.begin():
            lock(db, "password:" + digest("account:" + username))
            if not db.get(User, args.user_id):
                raise SystemExit("User does not exist")
            existing = db.scalar(select(LocalCredential).where(LocalCredential.username == username))
            if existing and existing.user_id != args.user_id:
                raise SystemExit("Username already assigned")
            credential = db.get(LocalCredential, args.user_id)
            if credential:
                credential.username, credential.password_hash = username, encoded
            else:
                db.add(LocalCredential(user_id=args.user_id, username=username, password_hash=encoded))
            db.execute(delete(AppSession).where(AppSession.user_id == args.user_id))
            db.execute(delete(LoginAttempt).where(LoginAttempt.key == digest("account:" + username)))
        print("Password saved; previous sessions revoked")
    elif args.command == "seed-development":
        seed_development()
    elif args.command == "provision-user":
        provision_user(args)
    else:
        with session_factory()() as db, db.begin():
            if args.command == "add-org":
                if args.parent_id and not db.get(OrgUnit, args.parent_id):
                    raise SystemExit("Parent organization does not exist")
                record = OrgUnit(name=args.name, parent_id=args.parent_id, unit_type=args.type)
            else:
                if args.start > args.end:
                    raise SystemExit("Invalid cycle dates")
                record = Cycle(name=args.name, start_date=args.start, end_date=args.end)
            db.add(record)
            db.flush()
            print(f"Created record ID {record.id}")


if __name__ == "__main__":
    main()
