"""
Seed script — creates sample Super Admin, Admin, and User accounts.

Run after applying Alembic migrations:
    python -m app.utils.seed
"""
import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.core.security import hash_password
from app.core.roles import Role


SEED_USERS = [
    {
        "username": "superadmin",
        "email": "superadmin@example.com",
        "password": "SuperAdmin@123",
        "role": Role.SUPER_ADMIN,
        "admin_id": None,
    },
    {
        "username": "bhargab",
        "email": "bhargab@example.com",
        "password": "12345678",
        "role": Role.ADMIN,
        "admin_id": None,
    },
    {
        "username": "user_nirodh",
        "email": "nirodh@example.com",
        "password": "12345678",
        "role": Role.USER,
        "admin_id": None,
    },
    {
        "username": "user_nilotpal",
        "email": "nilotpal@example.com",
        "password": "12345678",
        "role": Role.USER,
        "admin_id": None,
    },
]


async def ensure_superadmin(db):
    data = SEED_USERS[0]
    existing = await db.scalar(select(User).where(User.username == data["username"]))
    if existing:
        changed = False
        if existing.email != data["email"]:
            existing.email = data["email"]
            changed = True
        if existing.role != data["role"]:
            existing.role = data["role"]
            changed = True
        if not existing.hashed_password:
            existing.hashed_password = hash_password(data["password"])
            changed = True
        if changed:
            print(f"  [updated] {data['email']}  role={data['role']}")
        return existing

    user = User(
        username=data["username"],
        email=data["email"],
        hashed_password=hash_password(data["password"]),
        role=data["role"],
    )
    db.add(user)
    await db.flush()
    print(f"  [created] {data['email']}  role={data['role']}")
    return user


async def seed():
    async with AsyncSessionLocal() as db:
        created: dict[str, User] = {}

        for data in SEED_USERS:
            existing = await db.scalar(select(User).where(User.username == data["username"]))
            if existing:
                existing.email = data["email"]
                existing.hashed_password = hash_password(data["password"])
                existing.role = data["role"]
                print(f"  [updated] {data['email']}  role={data['role']}")
                created[data["username"]] = existing
                continue

            user = User(
                username=data["username"],
                email=data["email"],
                hashed_password=hash_password(data["password"]),
                role=data["role"],
            )
            db.add(user)
            await db.flush()
            created[data["username"]] = user
            print(f"  [created] {data['email']}  role={data['role']}")

        # Wire admin_id relationships
        # if "bhargab" in created and "superadmin" in created:
        #     # Admin is supervised by no one (super admin manages them directly)
        #     pass

        admin = created.get("bhargab")
        if admin:
            for uname in ("user_nirodh", "user_nilotpal"):
                u = created.get(uname)
                if u and u.admin_id is None:
                    u.admin_id = admin.id

        await db.commit()
        print("\nSeed complete. Credentials:")
        print("  superadmin@example.com    /  SuperAdmin@123")
        print("  bhargab@example.com       /  12345678")


if __name__ == "__main__":
    asyncio.run(seed())
