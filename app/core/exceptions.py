from fastapi import HTTPException, status


class AppException(HTTPException):
    """Base application exception."""
    def __init__(self, status_code: int, detail: str, headers: dict | None = None):
        super().__init__(status_code=status_code, detail=detail, headers=headers)


class NotFoundError(AppException):
    def __init__(self, resource: str = "Resource"):
        super().__init__(status.HTTP_404_NOT_FOUND, f"{resource} not found.")


class ForbiddenError(AppException):
    def __init__(self, detail: str = "You do not have permission to perform this action."):
        super().__init__(status.HTTP_403_FORBIDDEN, detail)


class UnauthorizedError(AppException):
    def __init__(self, detail: str = "Could not validate credentials."):
        super().__init__(
            status.HTTP_401_UNAUTHORIZED,
            detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class ConflictError(AppException):
    def __init__(self, detail: str = "Resource already exists."):
        super().__init__(status.HTTP_409_CONFLICT, detail)


class ValidationError(AppException):
    def __init__(self, detail: str):
        super().__init__(status.HTTP_422_UNPROCESSABLE_ENTITY, detail)


class FileTooLargeError(AppException):
    def __init__(self, max_mb: int):
        super().__init__(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File exceeds {max_mb} MB limit.")


class UnsupportedFileTypeError(AppException):
    def __init__(self, allowed: set):
        super().__init__(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Unsupported file type. Allowed: {', '.join(sorted(allowed))}")
