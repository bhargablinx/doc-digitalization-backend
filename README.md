# Doc Digitalization Backend

> FastAPI backend for document digitization and verification.

A FastAPI backend for digitizing physical forms with OCR extraction, JSONB storage, and role-based access control.

## Role Based Summary

| Action                   | User | Admin | Super Admin |
| ------------------------ | :--: | :---: | :---------: |
| Register / Login         |  ✓   |   ✓   |      ✓      |
| Upload document          |  ✓   |   ✓   |      ✓      |
| View own documents       |  ✓   |   ✓   |      ✓      |
| View supervised docs     |  ✗   |   ✓   |      ✓      |
| View all documents       |  ✗   |   ✗   |      ✓      |
| Correct extracted data   |  ✓   |   ✓   |      ✓      |
| Verify / Reject document |  ✗   |   ✓   |      ✓      |
| View audit trail         |  ✗   |   ✓   |      ✓      |
| Create / manage users    |  ✗   |  ✓\*  |      ✓      |
| Delete users             |  ✗   |   ✗   |      ✓      |

\*Admin can create up to 4 USER-role accounts, assigned to themselves.

## Database Setup Guide

### 1. Install PostgreSQL

**Ubuntu / Debian**

```bash
sudo apt install -y postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**macOS (Homebrew)**

```bash
brew install postgresql@16
brew services start postgresql@16
```

**Windows** — Download installer from https://www.postgresql.org/download/windows/

### 2. Create the database and user

```bash
sudo -u postgres psql
```

Inside `psql`:

```sql
CREATE USER docdigitalize_user WITH PASSWORD 'BB1234';
CREATE DATABASE docdigitalize OWNER docdigitalize_user;
GRANT ALL PRIVILEGES ON DATABASE docdigitalize TO docdigitalize_user;
\q
```

### 3. Verify connection

```bash
psql -U docdigitalize_user -d docdigitalize -h localhost -W
```

---

## Backend Setup Guide

### 1. Clone / unzip the project

```bash
cd docdigitalize
```

### 2. Create a Python virtual environment (Python 3.12+)

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env` — at minimum update these values:

```dotenv
SECRET_KEY=your-random-32-char-secret-key-here
DATABASE_URL=postgresql+asyncpg://docdigitalize_user:StrongPass!2024@localhost:5432/docdigitalize
DATABASE_URL_SYNC=postgresql://docdigitalize_user:StrongPass!2024@localhost:5432/docdigitalize
```

### 5. Run Alembic migrations

```bash
alembic upgrade head
```

Expected output:

```
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial, Initial schema
```

### 6. Seed / Load sample data

```bash
python -m app.utils.seed
```

Output:

```
Seed complete. Credentials:
  superadmin@example.com       /  SuperAdmin@123  (Super Admin)
  bhargab@example.com          /  12345678        (Admin)
  nirodh@example.com           /  12345678        (User)
  nilotpal@example.com         /  12345678        (User)
```

### 7. Start the server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Visit:

- **Swagger UI:** http://localhost:8000/docs

## API Reference

### Auth

#### Register

```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "username": "john_doe",
  "email": "john@example.com",
  "password": "Password@123"
}
```

**Response 201**

```json
{
    "id": 5,
    "username": "john_doe",
    "email": "john@example.com",
    "role": "user",
    "admin_id": null,
    "is_active": true,
    "created_at": "2024-06-10T08:00:00Z"
}
```

#### Login

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "bhargab@docdigitalize.local",
  "password": "User@12345"
}
```

**Response 200**

```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer"
}
```

#### Refresh token

```http
POST /api/v1/auth/refresh
Content-Type: application/json

{ "refresh_token": "<your-refresh-token>" }
```

#### Get current user

```http
GET /api/v1/auth/me
Authorization: Bearer <access_token>
```

---

### Documents

#### Upload a document

```http
POST /api/v1/documents
Authorization: Bearer <user_token>
Content-Type: multipart/form-data

file=@/path/to/form.pdf
```

**Response 201**

```json
{
    "id": 1,
    "user_id": 3,
    "original_filename": "form.pdf",
    "file_size_bytes": 102400,
    "mime_type": "application/pdf",
    "extracted_data": {
        "name": "Bhargab Bhuyan",
        "phone": "9876543210",
        "address": "Jorhat, Assam",
        "consumer_number": "123456",
        "_extraction_engine": "mock-v1",
        "_source_extension": ".pdf"
    },
    "status": "pending",
    "verified_by": null,
    "verification_remark": null,
    "verified_at": null,
    "uploaded_at": "2024-06-10T08:05:00Z"
}
```

#### List documents (with pagination)

```http
GET /api/v1/documents?page=1&page_size=10&status=pending
Authorization: Bearer <token>
```

**Response 200**

```json
{
  "total": 3,
  "page": 1,
  "page_size": 10,
  "items": [ ... ]
}
```

#### Get single document

```http
GET /api/v1/documents/1
Authorization: Bearer <token>
```

#### Correct extracted data manually

```http
PUT /api/v1/documents/1
Authorization: Bearer <token>
Content-Type: application/json

{
  "extracted_data": {
    "name": "Bhargab Bhuyan",
    "phone": "9876543210",
    "address": "Jorhat, Assam",
    "consumer_number": "654321"
  }
}
```

---

### Verification (Admin / Super Admin only)

#### Verify a document

```http
POST /api/v1/documents/1/verify
Authorization: Bearer <admin_token>
Content-Type: application/json

{ "remark": "All fields verified and correct." }
```

**Response 200**

```json
{
  "id": 1,
  "status": "verified",
  "verified_by": 2,
  "verification_remark": "All fields verified and correct.",
  "verified_at": "2024-06-10T09:00:00Z",
  ...
}
```

#### Reject a document

```http
POST /api/v1/documents/1/reject
Authorization: Bearer <admin_token>
Content-Type: application/json

{ "remark": "Consumer number is illegible. Please re-upload." }
```

#### View document audit trail

```http
GET /api/v1/documents/1/audit
Authorization: Bearer <admin_token>
```

**Response 200**

```json
[
    {
        "id": 1,
        "document_id": 1,
        "action": "uploaded",
        "performed_by": 3,
        "detail": "File: form.pdf",
        "timestamp": "2024-06-10T08:05:00Z"
    },
    {
        "id": 2,
        "document_id": 1,
        "action": "data_corrected",
        "performed_by": 3,
        "detail": "Manual correction",
        "timestamp": "2024-06-10T08:10:00Z"
    },
    {
        "id": 3,
        "document_id": 1,
        "action": "verified",
        "performed_by": 2,
        "detail": "All fields correct",
        "timestamp": "2024-06-10T09:00:00Z"
    }
]
```

---

### User Management (Admin / Super Admin)

#### List users

```http
GET /api/v1/users?page=1&page_size=20&role=user
Authorization: Bearer <admin_token>
```

#### Create a user (Super Admin assigns any role; Admin creates USER only)

```http
POST /api/v1/users
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "username": "new_user",
  "email": "newuser@example.com",
  "password": "Newpass@123",
  "role": "user",
  "admin_id": 2
}
```

#### Update a user

```http
PUT /api/v1/users/5
Authorization: Bearer <admin_token>
Content-Type: application/json

{ "is_active": false }
```

#### Delete a user (Super Admin only)

```http
DELETE /api/v1/users/5
Authorization: Bearer <superadmin_token>
```

## ENV Reference

| Variable                      | Default                     | Description                    |
| ----------------------------- | --------------------------- | ------------------------------ |
| `SECRET_KEY`                  | _(required)_                | JWT signing secret (≥32 chars) |
| `ALGORITHM`                   | `HS256`                     | JWT algorithm                  |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30`                        | Access token lifetime          |
| `REFRESH_TOKEN_EXPIRE_DAYS`   | `7`                         | Refresh token lifetime         |
| `DATABASE_URL`                | _(required)_                | Async PostgreSQL URL           |
| `DATABASE_URL_SYNC`           | _(required)_                | Sync URL (Alembic)             |
| `ALLOWED_ORIGINS`             | `http://localhost:5173`     | Comma-separated CORS origins   |
| `UPLOAD_DIR`                  | `uploads`                   | File storage root directory    |
| `MAX_FILE_SIZE_MB`            | `20`                        | Max upload size in MB          |
| `ALLOWED_EXTENSIONS`          | `pdf,png,jpg,jpeg,tiff,bmp` | Accepted file types            |
| `DEFAULT_PAGE_SIZE`           | `20`                        | Default pagination size        |
