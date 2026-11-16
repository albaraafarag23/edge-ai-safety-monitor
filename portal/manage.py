"""Portal chores from the server's command line (recovery when nobody can sign in).

    python manage.py invite <email> [--name "Albaraa Farag"]   new one-time setup link (makes an overseer if new)
    python manage.py people                                     everyone, with their role and devices
    python manage.py check-log                                  is the security log's chain intact?
"""
import argparse
import asyncio

from sqlalchemy import func, select
from webauthn.helpers import generate_user_handle

import audit
from main import new_invite
from models import Device, SessionLocal, User, create_tables


async def invite(email: str, name: str | None):
    email = email.strip().lower()
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if not user:
            user = User(email=email, name=name or "Overseer", role="overseer", handle=generate_user_handle())
            session.add(user)
            await session.commit()
            print(f"Made an overseer account for {email}")
    link = await new_invite(user, None)
    await audit.record("command line", "invite_link", f"A setup link for {user.name} was made on the server's "
                       "command line.", user.company_id, person_id=user.id)
    print(f"One-time setup link for {user.name} ({user.role}):\n{link}")


async def people():
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(User, func.count(Device.id)).outerjoin(Device, (Device.user_id == User.id)
                                                          & (Device.status == "approved")).group_by(User.id)
            .order_by(User.company_id, User.name))).all()
    for user, devices in rows:
        state = "" if user.active else "  (switched off)"
        print(f"{user.id:4}  {user.role:10}  {user.email:40}  {devices} device(s){state}")


async def main(args):
    await create_tables()
    if args.command == "invite":
        await invite(args.email, args.name)
    elif args.command == "people":
        await people()
    else:
        print(await audit.verify())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("invite")
    p.add_argument("email")
    p.add_argument("--name")
    sub.add_parser("people")
    sub.add_parser("check-log")
    asyncio.run(main(parser.parse_args()))
