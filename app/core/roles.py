from enum import StrEnum


class Role(StrEnum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    USER = "user"


ROLE_HIERARCHY: dict[Role, int] = {
    Role.USER: 0,
    Role.ADMIN: 1,
    Role.SUPER_ADMIN: 2,
}

ADMIN_USER_LIMIT = 4