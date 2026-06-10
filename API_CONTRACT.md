# Document Upload API

## Endpoint

POST /upload

---

## Request

Content-Type:

multipart/form-data

Field Name:

file

Supported Formats:

* PDF
* JPG
* JPEG
* PNG

Example:

```javascript
const formData = new FormData();
formData.append("file", selectedFile);
```

---

## Success Response

```json
{
  "success": true,
  "filename": "sample.pdf",
  "data": {
    "Name": "Nilotpal Baishya",
    "Age": "21"
  }
}
```

---

## Error Response

```json
{
  "success": false,
  "error": "error message"
}
```
