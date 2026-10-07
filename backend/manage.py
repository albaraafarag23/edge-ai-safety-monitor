"""Dashboard accounts from the command line.

    docker compose exec backend python manage.py create-user ana@site.com "Ana Lopez" --role supervisor
    docker compose exec backend python manage.py set-password ana@site.com
    docker compose exec backend python manage.py list-users

Passwords are asked for interactively, so they don't end up in the shell history.
"""
import argparse
import asyncio
import getpass

from sqlalchemy import select

import auth
from models import Base, SessionLocal, User, engine


def ask_password() -> str:
    while True:
        password = getpass.getpass("Password (min 8 characters): ")
        if len(password) < 8:
            print("Too short.")
        elif password != getpass.getpass("Repeat: "):
            print("Doesn't match.")
        else:
            return password


async def main(args):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    if args.command == "create-user":
        user = await auth.create_user(args.email, args.name, ask_password(), args.role)
        print(f"Created {user.role} {user.email}")
    elif args.command == "set-password":
        async with SessionLocal() as session:
            user = await session.scalar(select(User).where(User.email == args.email.strip().lower()))
            if not user:
                raise SystemExit(f"No user {args.email}")
            user.password_hash = auth.hash_password(ask_password())
            await session.commit()
        print(f"Password changed for {args.email}")
    elif args.command == "list-users":
        async with SessionLocal() as session:
            for u in (await session.scalars(select(User).order_by(User.id))).all():
                print(f"{u.id:>3}  {u.role:<10}  {'active' if u.active else 'disabled':<8}  {u.email}  ({u.name})")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-user")
    create.add_argument("email")
    create.add_argument("name")
    create.add_argument("--role", choices=auth.ROLES, default="supervisor")
    sub.add_parser("set-password").add_argument("email")
    sub.add_parser("list-users")
    asyncio.run(main(parser.parse_args()))
