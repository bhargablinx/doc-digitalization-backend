from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserListResponse
from app.core.security import hash_password
from app.core.roles import Role, ADMIN_USER_LIMIT
from app.core.exceptions import NotFoundError, ConflictError, ForbiddenError, ValidationError
from app.api.deps import CurrentUser, require_role, require_min_role
from app.core.config import settings

router = APIRouter(prefix="/users", tags=["Users"])

AdminOrAbove = require_min_role(Role.ADMIN)
SuperAdminOnly = require_role(Role.SUPER_ADMIN)


@router.get("", response_model=UserListResponse)
async def list_users(
    current_user: CurrentUser,
    _: Annotated[User, AdminOrAbove],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    role: Role | None = None,
):
    """
    Super admin sees all users.
    Admin sees only their assigned users.
    """
    q = select(User)
    if current_user.role == Role.ADMIN:
        q = q.where(User.admin_id == current_user.id)
    if role:
        q = q.where(User.role == role)

    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    result = await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    users = result.scalars().all()

    return UserListResponse(total=total or 0, page=page, page_size=page_size, items=list(users))


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: CurrentUser,
    _: Annotated[User, AdminOrAbove],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await _fetch_user_or_404(user_id, db)
    _assert_access(current_user, user)
    return user


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    payload: UserCreate,
    current_user: CurrentUser,
    _: Annotated[User, AdminOrAbove],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Super admin can create any role.
    Admin can only create USER-role accounts assigned to themselves.
    """
    if current_user.role == Role.ADMIN:
        if payload.role != Role.USER:
            raise ForbiddenError("Admins can only create regular users.")
        payload.admin_id = current_user.id
        # Enforce 4-user cap
        count = await db.scalar(
            select(func.count()).where(User.admin_id == current_user.id, User.is_active == True)
        )
        if (count or 0) >= ADMIN_USER_LIMIT:
            raise ValidationError(f"Admin already supervises the maximum of {ADMIN_USER_LIMIT} users.")

    existing = await db.execute(
        select(User).where((User.email == payload.email) | (User.username == payload.username))
    )
    if existing.scalar_one_or_none():
        raise ConflictError("A user with that email or username already exists.")

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        admin_id=payload.admin_id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    current_user: CurrentUser,
    _: Annotated[User, AdminOrAbove],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await _fetch_user_or_404(user_id, db)
    _assert_access(current_user, user)

    for field, value in payload.model_dump(exclude_none=True, exclude={"password"}).items():
        setattr(user, field, value)
    if payload.password:
        user.hashed_password = hash_password(payload.password)

    await db.flush()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    current_user: CurrentUser,
    _: Annotated[User, SuperAdminOnly],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await _fetch_user_or_404(user_id, db)
    await db.delete(user)


# Helpers
async def _fetch_user_or_404(user_id: int, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User")
    return user


def _assert_access(current_user: User, target: User) -> None:
    """Admins can only touch their own assigned users."""
    if current_user.role == Role.ADMIN and target.admin_id != current_user.id:
        raise ForbiddenError("You can only manage users assigned to you.")
