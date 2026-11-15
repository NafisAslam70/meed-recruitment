# MEED Recruitment

A Flask recruitment portal for MEED Public School. It provides application forms for teaching and administrative vacancies, with PDF CV upload and candidate-detail extraction to help staff review submissions.

## Features
- Candidate application form
- PDF CV upload, text extraction, and OCR fallback for scanned pages
- Extracted contact details for review
- Teacher search/review page
- Session-based web interface

## Tech
Python, Flask, pdfplumber, Tesseract OCR, pdf2image, spaCy, and phonenumbers.

## Run locally
```bash
pip install -r requirements.txt
python app.py
```

Install the required PDF/OCR utilities and spaCy English model. Set `SECRET_KEY`, `ADMIN_USERNAME`, and `ADMIN_PASSWORD` securely before deployment.
