from flask import Flask, request, render_template, jsonify, send_from_directory, session, redirect, url_for
import os
import re
from werkzeug.utils import secure_filename
import pdfplumber
from pdf2image import convert_from_path
import pytesseract
from urllib.parse import quote
from flask_session import Session
import requests
from bs4 import BeautifulSoup
import spacy
import phonenumbers
from email_validator import validate_email, EmailNotValidError
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    filename='app.log',
    format='%(asctime)s %(levelname)s: %(message)s',
    filemode='a'
)

app = Flask(__name__)

# Load spaCy model with error handling
try:
    nlp = spacy.load('en_core_web_sm')
    logging.info("Successfully loaded spaCy model 'en_core_web_sm'")
except OSError as e:
    logging.error(f"Failed to load spaCy model: {str(e)}. Falling back to regex-only name extraction.")
    nlp = None

# Configure session
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(os.getcwd(), 'flask_session')
Session(app)

# Configure upload directory
UPLOAD_FOLDER = 'Uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
YOUR_WHATSAPP_NUMBER = '+601112079684'

# Ensure upload directory exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Hardcoded credentials (move to env vars in production)
HARDCODED_CREDENTIALS = {
    'username': os.environ.get('ADMIN_USERNAME', 'admin'),
    'password': os.environ.get('ADMIN_PASSWORD', 'password123')
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def normalize_phone_number(number):
    try:
        parsed_number = phonenumbers.parse(number, 'IN')
        if phonenumbers.is_valid_number(parsed_number):
            normalized = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
            logging.info(f"Normalized phone number: {normalized}")
            return normalized
    except phonenumbers.NumberParseException as e:
        logging.error(f"Phone number parsing failed: {str(e)}")
        return None
    return None

def extract_info(file_path):
    text = ''
    # Step 1: Check if PDF is scanned (image-based)
    try:
        images = convert_from_path(file_path, first_page=1, last_page=1)
        if images:
            text = pytesseract.image_to_string(images[0])
            logging.info("Extracted text from scanned PDF using OCR")
    except Exception as e:
        logging.error(f"OCR extraction failed: {str(e)}")

    # Step 2: Use pdfplumber for text-based PDFs
    if not text:
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + ' '
            logging.info("Extracted text from PDF using pdfplumber")
        except Exception as e:
            logging.error(f"pdfplumber extraction failed: {str(e)}")

    if not text.strip():
        logging.warning("No text extracted from PDF")
        return '', '', ''

    # Step 3: Text normalization
    text = re.sub(r'\s+', ' ', text).strip().lower()

    # Step 4: Name extraction with NER (if available) or regex
    name = ''
    if nlp:
        try:
            doc = nlp(text)
            for ent in doc.ents:
                if ent.label_ == 'PERSON' and len(ent.text.split()) <= 3:
                    name = ent.text.title()
                    logging.info(f"Extracted name using spaCy: {name}")
                    break
        except Exception as e:
            logging.error(f"spaCy NER failed: {str(e)}")

    if not name:
        name_patterns = [
            r'Name\s*[:\-]?\s*([A-Za-z\s]+(?:[A-Za-z]\.)?)',
            r'Full\s*Name\s*[:\-]?\s*([A-Za-z\s]+(?:[A-Za-z]\.)?)',
            r'^(?:Mr\.?|Ms\.?|Mrs\.?)\s*([A-Z][a-zA-Z]*\s+[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*)',
            r'^([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*){1,2})'
        ]
        for pattern in name_patterns:
            name_match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if name_match:
                words = name_match.group(1).split()
                filtered_words = [word for word in words if not re.match(r'boond[A-Za-z]*|Teacher', word, re.IGNORECASE)]
                name = ' '.join(filtered_words[:3]).title()
                if name.strip():
                    logging.info(f"Extracted name using regex: {name}")
                    break
        if not name:
            name_match = re.search(r'^([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*){1,2})', text, re.MULTILINE)
            if name_match:
                name = name_match.group(1).title()
                logging.info(f"Extracted fallback name using regex: {name}")

    # Step 5: Email extraction with validation
    email = ''
    email_patterns = [
        r'Email\s*[:\-]?\s*([\w\.-]+@[\w\.-]+\.\w{2,})',
        r'E-mail\s*[:\-]?\s*([\w\.-]+@[\w\.-]+\.\w{2,})',
        r'[\w\.-]+@[\w\.-]+\.\w{2,}(?=\s|$)'
    ]
    for pattern in email_patterns:
        email_match = re.search(pattern, text, re.IGNORECASE)
        if not email_match:
            continue
        try:
            email_candidate = email_match.group(1) if email_match.lastindex else email_match.group(0)
            email_candidate = email_candidate.strip()
            validate_email(email_candidate, check_deliverability=False)
            email = email_candidate
            logging.info(f"Extracted email: {email}")
            break
        except (EmailNotValidError, IndexError) as e:
            logging.error(f"Email validation failed: {str(e)}")

    # Step 6: Phone extraction with validation
    phone = ''
    phone_pattern = r'\+?\d{1,3}[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}|\d{10}'
    phone_numbers = re.findall(phone_pattern, text)
    for number in phone_numbers:
        normalized = normalize_phone_number(number)
        if normalized:
            phone = normalized
            logging.info(f"Extracted phone: {phone}")
            break

    return name, email, phone

def generate_message(name):
    if not name:
        name = "Applicant"
        logging.info("Using default name 'Applicant' for message generation")
    return (
        f"Dear {name},\n\n"
        f"We’re hiring at MEED Public School, a well-reputed institution near New Farakka!\n\n"
        f"🟢 Urgent Vacancies Available:\n"
        f"Teachers – Junior Section (All Subjects)\n"
        f"Teachers – Senior Section (All Subjects)\n"
        f"Office Manager – Male candidates only (Must be skilled in MS Word, Excel, Photoshop, etc.)\n"
        f"Hostel Warden / Helper\n\n"
        f"🏠 Free Fooding & Lodging Provided\n\n"
        f"If interested, kindly send your CV via WhatsApp or Email:\n"
        f"📲 +60 11-1207 9684 (Malaysia – Main Contact)\n"
        f"📲 +91 99233 14480 (School Office)\n"
        f"📧 mymeedpss@gmail.com\n\n"
        f"🌐 Visit: www.mymeedpss.com for more info\n"
        f"📞 Call us immediately at the school number: +91 99233 14480\n\n"
        f"Feel free to contact us anytime.\n"
        f"— Superintendent, MEED Public School"
    )

def scrape_teaching_jobs():
    try:
        url = "https://www.quikr.com/jobs/hire/shortlist"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        }
        session_cookie = os.environ.get('QUIKR_SESSION_COOKIE', 'your_quikr_session_cookie')
        response = requests.get(url, headers=headers, cookies={'session': session_cookie})
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        candidates = []
        
        candidate_cards = soup.select('.shortlisted-candidate')
        for card in candidate_cards[:10]:
            name_elem = card.select_one('.candidate-name')
            resume_elem = card.select_one('.download-resume')
            view_contact_elem = card.select_one('.view-contact')
            
            name = name_elem.text.strip() if name_elem else 'N/A'
            has_resume = bool(resume_elem)
            contact_info = None
            
            if view_contact_elem and 'href' in view_contact_elem.attrs:
                contact_url = view_contact_elem['href']
                contact_response = requests.get(contact_url, headers=headers, cookies={'session': session_cookie})
                contact_soup = BeautifulSoup(contact_response.text, 'html.parser')
                phone = contact_soup.select_one('.phone-number')
                email = contact_soup.select_one('.email')
                contact_info = {
                    'phone': phone.text.strip() if phone else 'N/A',
                    'email': email.text.strip() if email else 'N/A'
                }
            
            candidate = {
                'name': name,
                'has_resume': has_resume,
                'contact': contact_info
            }
            candidates.append(candidate)
        
        logging.info(f"Scraped {len(candidates)} candidates from Quikr")
        return candidates
    except Exception as e:
        logging.error(f"Error scraping jobs: {str(e)}")
        return [
            {'name': 'Sample Teacher JH', 'has_resume': True, 'contact': {'phone': '+919876543210', 'email': 'teacher.jh@example.com'}},
            {'name': 'Sample Teacher WB', 'has_resume': False, 'contact': {'phone': '+918765432109', 'email': 'teacher.wb@example.com'}}
        ]

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if (username == HARDCODED_CREDENTIALS['username'] and 
            password == HARDCODED_CREDENTIALS['password']):
            session['logged_in'] = True
            logging.info(f"User logged in: {username}")
            return redirect(url_for('index'))
        else:
            error = 'Invalid username or password'
            logging.warning(f"Failed login attempt: username={username}")
            return render_template('login.html', error=error)
    
    return render_template('login.html', error='')

@app.route('/find-teachers')
def find_teachers():
    if not session.get('logged_in'):
        logging.info("Redirecting unauthenticated user to login from /find-teachers")
        return redirect(url_for('login'))
    
    candidates = scrape_teaching_jobs()
    return render_template('find_teachers.html', candidates=candidates)

@app.route('/', methods=['GET', 'POST'])
def index():
    if not session.get('logged_in'):
        logging.info("Redirecting unauthenticated user to login from /")
        return redirect(url_for('login'))
    
    message = ''
    error = ''
    pdf_path = ''
    whatsapp_number = ''
    contact_link = ''
    source = ''
    name = ''
    email = ''
    phone = ''
    fetched_name = ''
    fetched_email = ''
    fetched_phone = ''

    if request.method == 'POST':
        if 'resume' in request.files:
            file = request.files['resume']
            source = 'pdf'
            
            if file.filename == '':
                error = 'No file selected'
                logging.warning("No file selected for PDF upload")
            elif file and allowed_file(file.filename):
                file.seek(0, os.SEEK_END)
                file_size = file.tell()
                if file_size > MAX_FILE_SIZE:
                    error = 'File size exceeds 10MB limit'
                    logging.warning(f"File size exceeds limit: {file_size} bytes")
                else:
                    file.seek(0)
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    
                    try:
                        file.save(filepath)
                        pdf_path = f"/Uploads/{filename}"
                        logging.info(f"Saved PDF: {filename}")
                        fetched_name, fetched_email, fetched_phone = extract_info(filepath)
                        name = fetched_name
                        email = fetched_email
                        phone = fetched_phone
                        message = generate_message(name)
                        if not (name or email or phone):
                            error = 'Could not extract details from PDF. Please enter manually.'
                            logging.warning("No details extracted from PDF")
                    except Exception as e:
                        logging.error(f"PDF processing error: {str(e)}")
                        error = 'Failed to process PDF. Please ensure it is a valid, readable PDF or enter details manually.'
        
        elif 'name' in request.form:
            source = 'text'
            name = request.form.get('name', '')
            email = request.form.get('email', '')
            phone = request.form.get('phone', '')
            
            if name:
                message = generate_message(name)
                whatsapp_number = normalize_phone_number(phone) if phone else None
                if whatsapp_number:
                    contact_link = f"https://wa.me/{whatsapp_number}?text={quote(message)}"
                    logging.info(f"Generated WhatsApp link for phone: {whatsapp_number}")
                else:
                    error = 'No valid phone number provided' if phone else 'No phone number provided'
                    logging.warning(f"Invalid or missing phone number: {phone}")
                    contact_link = f"mailto:mymeedpss@gmail.com?subject=Job%20Application%20-%20{name}&body=Please%20attach%20your%20CV"
        
        else:
            error = 'No valid input provided'
            logging.warning("No valid input provided in POST request")
        
        return render_template('index.html', error=error, message=message, pdf_path=pdf_path, 
                             whatsapp_number=whatsapp_number, contact_link=contact_link, source=source,
                             name=name, email=email, phone=phone,
                             fetched_name=fetched_name, fetched_email=fetched_email, fetched_phone=fetched_phone)
    
    return render_template('index.html', error=error, message=message, pdf_path=pdf_path, 
                         whatsapp_number=whatsapp_number, contact_link=contact_link, source=source,
                         name=name, email=email, phone=phone,
                         fetched_name=fetched_name, fetched_email=fetched_email, fetched_phone=fetched_phone)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    logging.info("User logged out")
    return redirect(url_for('login'))

@app.route('/Uploads/<filename>')
def serve_uploaded_file(filename):
    if not session.get('logged_in'):
        logging.info("Redirecting unauthenticated user to login from /Uploads")
        return redirect(url_for('login'))
    logging.info(f"Serving file: {filename}")
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/cleanup', methods=['GET'])
def cleanup():
    if not session.get('logged_in'):
        logging.info("Redirecting unauthenticated user to login from /cleanup")
        return redirect(url_for('login'))
    file_path = request.args.get('file')
    if file_path:
        full_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(file_path))
        try:
            if os.path.exists(full_path):
                os.remove(full_path)
                logging.info(f"Deleted file: {full_path}")
            else:
                logging.warning(f"File not found for deletion: {full_path}")
        except Exception as e:
            logging.error(f"Failed to delete file: {str(e)}")
    return jsonify({"status": "success"})

@app.route('/debug-routes')
def debug_routes():
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'rule': str(rule)
        })
    logging.info("Accessed debug-routes endpoint")
    return jsonify(routes)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5800))
    app.run(host='0.0.0.0', port=port, debug=True)