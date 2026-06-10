from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware

import shutil

from app.services.document_service import process_document

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/extract")
async def upload_file(file: UploadFile):

    try:

        file_path = f"app/uploads/{file.filename}"

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        data = process_document(
            file_path=file_path,
            filename=file.filename
        )

        return {
            "success": True,
            "filename": file.filename,
            "data": data
        }

    except Exception as e:

        return {
            "success": False,
            "error": str(e)
        }