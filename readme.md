# Doc Digitalization Backend

FastAPI backend for document digitization and verification.

## Features

* PDF text extraction using pdfplumber
* OCR extraction using Tesseract OCR
* PDF parsing
* OCR parsing
* Structured JSON response
* File upload API
* CORS enabled for frontend integration

## Tech Stack

* FastAPI
* Python
* pdfplumber
* pytesseract
* Pillow

## Setup

### Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Install Tesseract

Ubuntu:

```bash
sudo apt update
sudo apt install tesseract-ocr
```

### Run Server

```bash
uvicorn app.main:app --reload
```

Server runs on:

```text
http://localhost:8000
```

## API Endpoint

### Upload Document

```http
POST /upload
```

Supports:

* PDF
* JPG
* JPEG
* PNG

### Response

```json
{
  "success": true,
  "filename": "sample.pdf",
  "data": {
    "Name": "John Doe"
  }
}
```

## Future Roadmap

* Database integration
* User/Admin authentication
* Document storage
* Admin review workflow
* Offline LAN deployment
