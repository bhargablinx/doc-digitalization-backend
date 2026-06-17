# Project Context: DocDigitalize Backend

## Overview

This repository is a backend-only FastAPI service for document digitization and verification. It supports:

- JWT auth with access and refresh tokens
- role-based access control for `user`, `admin`, and `super_admin`
- local file uploads
- OCR/text extraction from uploaded documents
- storing extracted fields in PostgreSQL `JSONB`
- manual correction of extracted data
- admin verification/rejection workflows
- audit logging of document activity

The API is mounted under `/api/v1`. Swagger is available at `/docs`, ReDoc at `/redoc`, and health check at `/health`.

## Stack

- Python 3.12+ expected by README
- FastAPI + Uvicorn
- SQLAlchemy 2.x async ORM
- PostgreSQL + Alembic
- Pydantic v2 + `pydantic-settings`
- `python-jose` for JWT
- `bcrypt` for password hashing
- `aiofiles` for async file writes
- `pdfplumber` for PDF text extraction
- `pytesseract` + `Pillow` for image OCR

Operational note:

- `pytesseract` also requires the Tesseract system binary to be installed. The repo does not automate that setup.

## Repository Layout

- `app/main.py`: app factory, CORS, exception handlers, health route
- `app/api/`: routes and auth dependencies
- `app/core/`: config, security, roles, custom exceptions
- `app/db/`: async engine, session factory, declarative base
- `app/models/`: SQLAlchemy ORM models
- `app/schemas/`: Pydantic request/response models
- `app/services/`: local storage and extraction logic
- `app/utils/seed.py`: seed script
- `alembic/`: migration config and versions
- `README.md`: setup and API usage docs
- `.env.sample`: env template
- `uploads/`: default local upload directory

There are no tests in the repository right now.

## App Boot and Runtime Behavior

The app is created in `app/main.py` with:

- title from `settings.APP_NAME`
- CORS origins from `settings.allowed_origins_list`
- custom exception handler for app-specific HTTP exceptions
- custom handler for validation errors
- router registration via `app.api.api_router`

The app does not define complex startup/shutdown hooks. It is a small, request-driven service.

## Configuration

Config is defined in `app/core/config.py` and loaded from `.env` via `pydantic-settings`.

Main settings:

- `APP_NAME`
- `APP_ENV`
- `DEBUG`
- `SECRET_KEY`
- `ALGORITHM`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `REFRESH_TOKEN_EXPIRE_DAYS`
- `DATABASE_URL`
- `DATABASE_URL_SYNC`
- `ALLOWED_ORIGINS`
- `UPLOAD_DIR`
- `MAX_FILE_SIZE_MB`
- `ALLOWED_EXTENSIONS`
- `DEFAULT_PAGE_SIZE`
- `MAX_PAGE_SIZE`

Derived helpers:

- `allowed_origins_list`
- `allowed_extensions_set`
- `max_file_size_bytes`

Important defaults in code:

- app name: `DocDigitalize`
- env: `development`
- debug: `True`
- access token expiry: 30 minutes
- refresh token expiry: 7 days
- upload dir: `uploads`
- max file size: 20 MB

Security note:

- `SECRET_KEY` has an insecure fallback in code and must be overridden outside development.

## Database and Data Model

The project uses PostgreSQL and Alembic. The schema is initialized by `alembic/versions/0001_initial.py`.

### `users`

Model: `app/models/user.py`

Fields:

- `id`
- `username` unique, indexed
- `email` unique, indexed
- `hashed_password`
- `role` as enum `role_enum`
- `is_active`
- `admin_id` nullable self-reference to another user
- `created_at`

Relationships:

- `supervisor`
- `supervised_users`
- `documents`
- `verified_documents`
- `audit_logs`

### `documents`

Model: `app/models/document.py`

Fields:

- `id`
- `user_id`
- `file_path`
- `original_filename`
- `file_size_bytes`
- `mime_type`
- `extracted_data` as `JSONB`
- `status` as enum `doc_status_enum`
- `verified_by`
- `verification_remark`
- `verified_at`
- `uploaded_at`

Status values:

- `pending`
- `verified`
- `rejected`

Relationships:

- `uploader`
- `verifier`
- `audit_logs`

### `audit_logs`

Model: `app/models/audit_log.py`

Fields:

- `id`
- `document_id`
- `action`
- `performed_by`
- `detail`
- `timestamp`

Purpose:

- Tracks important document actions such as upload, correction, verification, and rejection.

## Roles and Access Model

Roles are defined in `app/core/roles.py`:

- `user`
- `admin`
- `super_admin`

Hierarchy:

- `user` = 0
- `admin` = 1
- `super_admin` = 2

Admin-specific limit:

- `ADMIN_USER_LIMIT = 4`

Access is enforced through:

- bearer auth in `app/api/deps.py`
- `get_current_user()`
- `require_role(...)`
- `require_min_role(...)`
- route-specific access checks like `_assert_access()` and `_assert_doc_access()`

Practical permission model:

- `user`: can register/login, upload documents, view/update their own documents, cannot verify/reject or manage users
- `admin`: can manage only assigned users, create only `user` accounts, supervise up to 4 active users, view and process their own plus supervised users' documents
- `super_admin`: unrestricted across users and documents, including delete-user access

## Auth and Security

Security helpers live in `app/core/security.py`.

Behavior:

- passwords are hashed and verified with `bcrypt`
- access and refresh JWTs are signed with `SECRET_KEY` and `ALGORITHM`
- token claims include `sub`, `type`, and `exp`
- access tokens also carry the role at issuance time

Auth routes in `app/api/endpoints/auth.py`:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/auth/me`

Validation rules:

- username length: 3 to 64
- username chars: letters, digits, `_`, `-`
- password minimum: 8 chars
- email validated by Pydantic

Behavior notes:

- register always creates a regular `user`
- login and refresh only work for active users
- missing or invalid bearer tokens return `401`

## DB Session Pattern

`app/db/session.py` creates the async engine and request-scoped `AsyncSession`.

Each request:

- receives a DB session through dependency injection
- commits automatically if the request finishes successfully
- rolls back on exception
- always closes the session

Routes therefore usually call `flush()` and `refresh()` but do not call `commit()` directly.

## Document Workflow

Primary logic is in `app/api/endpoints/documents.py`.

Upload flow:

1. Authenticated user uploads a multipart file.
2. `save_upload()` validates extension and file size.
3. File is stored at `UPLOAD_DIR/<user_id>/<YYYY/MM/DD>/<uuid>.<ext>`.
4. A `Document` row is created with status `pending`.
5. `process_document()` extracts and parses text.
6. Parsed data is saved to `document.extracted_data`.
7. An `AuditLog` row is created with action `uploaded`.
8. The document is returned.

Manual correction:

- `PUT /api/v1/documents/{doc_id}` replaces `extracted_data`
- allowed for accessible documents
- blocked if the document is already `verified`
- creates audit action `data_corrected`

Review workflow:

- `POST /api/v1/documents/{doc_id}/verify` sets status to `verified`
- `POST /api/v1/documents/{doc_id}/reject` sets status to `rejected`
- both store verifier, timestamp, and remark
- both create matching audit entries

Access rules:

- users can access only their own documents
- admins can access their own documents plus documents of supervised users
- super admins can access all documents

Important behavior:

- rejected documents can still be updated because only `verified` is blocked from editing

## Storage and Extraction Services

### Storage

Implemented in `app/services/storage.py`.

Behavior:

- validates extension against configured allow-list
- reads the whole file into memory
- rejects files larger than `MAX_FILE_SIZE_MB`
- writes to local disk using `aiofiles`
- returns file path, size, and MIME type

Default allowed upload extensions:

- `pdf`
- `png`
- `jpg`
- `jpeg`
- `tiff`
- `bmp`

### Extraction

Implemented in `app/services/extraction.py`.

Behavior:

- extracts text from the saved file
- parses key/value style fields
- returns a dictionary
- adds `_source_file` to the result

Supported extraction sources:

- PDF via `pdfplumber`
- images via `pytesseract`
- `.txt` and `.md` via direct file reads

Note:

- `.txt` and `.md` are supported by the extraction service but not by the upload allow-list.

Field parsing behavior:

- known aliases normalize to `name`, `phone`, `address`, `consumer_number`
- unknown keys are preserved after snake_case normalization
- accepted styles include `Name: Value`, `Name - Value`, and `Name Value`
- multi-line values are supported

## API Summary

### Auth

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/auth/me`

### Documents

- `POST /api/v1/documents`: upload
- `GET /api/v1/documents`: paginated list with optional `status` and `user_id`
- `GET /api/v1/documents/{doc_id}`: fetch one
- `PUT /api/v1/documents/{doc_id}`: replace extracted data
- `POST /api/v1/documents/{doc_id}/verify`
- `POST /api/v1/documents/{doc_id}/reject`
- `GET /api/v1/documents/{doc_id}/audit`

### Users

- `GET /api/v1/users`
- `GET /api/v1/users/{user_id}`
- `POST /api/v1/users`
- `PUT /api/v1/users/{user_id}`
- `DELETE /api/v1/users/{user_id}`

User-management behavior:

- admins and super admins can list users
- admins only see/manage assigned users
- super admins can create any role
- admins can create only `user` accounts and those are forced to `admin_id=current_admin`
- admins cannot exceed 4 active supervised users
- only super admins can delete users

Implementation caveats:

- user updates do not pre-check unique email/username before commit
- admin updates do not explicitly block changing a supervised user's role
- document audit endpoint uses `response_model=list` even though `AuditLogResponse` exists

## Schemas and Error Handling

Pydantic schemas live in `app/schemas/`:

- `auth.py`
- `user.py`
- `document.py`
- `audit_log.py`

Response models use `from_attributes=True`, so ORM objects are serialized directly.

`DocumentResponse.extracted_data` is intentionally loose: `Optional[dict[str, Any]]`.

Custom exceptions in `app/core/exceptions.py` map to:

- `NotFoundError` -> 404
- `ForbiddenError` -> 403
- `UnauthorizedError` -> 401
- `ConflictError` -> 409
- `ValidationError` -> 422
- `FileTooLargeError` -> 413
- `UnsupportedFileTypeError` -> 415

In `app/main.py`, app exceptions return `{"detail": ...}` and validation errors return Pydantic/FastAPI `exc.errors()`.

## Migrations and Seeding

Alembic is configured through `alembic.ini` and `alembic/env.py`, using `settings.DATABASE_URL_SYNC`.

Current migration history:

- `0001_initial`: creates enums, `users`, `documents`, `audit_logs`, and indexes

Seed script:

- run with `python -m app.utils.seed`
- creates or updates one super admin, one admin, and two regular users
- assigns the two regular users to the seeded admin

Seed identities:

- `superadmin@example.com` / `SuperAdmin@123`
- `bhargab@example.com` / `12345678`
- `nirodh@example.com` / `12345678`
- `nilotpal@example.com` / `12345678`

Note:

- the seed script prints only the first two credentials at the end even though it seeds four users

## Setup Flow

Typical local setup:

1. Create and activate a virtual environment.
2. Install `requirements.txt`.
3. Copy `.env.sample` to `.env`.
4. Set DB URLs and `SECRET_KEY`.
5. Run `alembic upgrade head`.
6. Optionally run `python -m app.utils.seed`.
7. Start with `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`.

## Known Drift, Risks, and Caveats

- `README.md` says `cp .env.example .env`, but the repo contains `.env.sample`
- README still mentions older mock extraction metadata like `_extraction_engine: "mock-v1"`, while current code adds `_source_file`
- `.gitignore` ignores `app/uploads/*`, but the default upload directory is top-level `uploads/`
- no automated tests exist even though pytest dependencies are present
- uploads are fully read into memory before being written
- OCR for images depends on external Tesseract installation
- `DocumentStatus` exists in `app/models/document.py` but is unused; `DocStatus` is the real enum
- `app/main.py` still has a comment saying setup needs improvement

## Best Mental Model for Another AI

Treat this as a small FastAPI monolith with clear layers and a simple workflow:

- authenticate user
- upload document
- extract text into structured JSON
- let user/admin correct data
- let admin/super admin verify or reject
- record each important action in audit logs

The codebase is compact and readable, with local file storage instead of cloud storage, flexible extracted-data shape via `JSONB`, and a permission model centered on ownership and admin supervision. It is functional, but still early-stage because it lacks tests, has a few documentation mismatches, and has some validation/permission hardening opportunities.
