from flask import Flask, request, render_template, jsonify, send_from_directory, session, redirect, url_for
import os
import re
from werkzeug.utils import secure_filename
import PyPDF2
from urllib.parse import quote
from flask_session import Session
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

# Configure session
app.config['SECRET_KEY'] = 'your-secret-key'  # Replace with a secure key in production
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(os.getcwd(), 'flask_session')
Session(app)

# Configure upload directory
UPLOAD_FOLDER = 'Uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'pdf'}
YOUR_WHATSAPP_NUMBER = '+601112079684'

# Ensure upload directory exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Hardcoded credentials
HARDCODED_CREDENTIALS = {
    'username': 'admin',
    'password': 'password123'
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def normalize_phone_number(number):
    number = re.sub(r'[-.\s]', '', number)
    if not re.match(r'^\+?\d{10,12}$', number):
        return None
    return number if number.startswith('+') else f'+91{number}'

def extract_info(text):
    # Robust name extraction
    name = ''
    name_patterns = [
        r'Name\s*[:\-]?\s*([A-Za-z\s]+(?:[A-Za-z]\.)?)',  # Name: John Doe or Name: Mr. J. Doe
        r'Full\s*Name\s*[:\-]?\s*([A-Za-z\s]+(?:[A-Za-z]\.)?)',  # Full Name: John Doe
        r'^(?:Mr\.?|Ms\.?|Mrs\.?)\s*([A-Z][a-zA-Z]*\s+[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*)'  # Mr. John Doe at start
    ]
    for pattern in name_patterns:
        name_match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if name_match:
            words = name_match.group(1).split()
            filtered_words = [word for word in words if not re.match(r'boond[A-Za-z]*|Teacher', word, re.IGNORECASE)]
            name = ' '.join(filtered_words[:3])  # Limit to 3 words
            if name.strip():
                break
    if not name:
        # Fallback to capitalized words at start
        name_match = re.search(r'^([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*){1,2})', text, re.MULTILINE)
        if name_match:
            name = name_match.group(1)

    # Robust email extraction
    email = ''
    email_patterns = [
        r'Email\s*[:\-]?\s*([\w\.-]+@[\w\.-]+\.\w{2,})',  # Email: name@domain.com
        r'E-mail\s*[:\-]?\s*([\w\.-]+@[\w\.-]+\.\w{2,})',  # E-mail: name@domain.com
        r'[\w\.-]+@[\w\.-]+\.\w{2,}(?=\s|$)'  # Standalone email (e.g., name@domain.com)
    ]
    for pattern in email_patterns:
        email_match = re.search(pattern, text, re.IGNORECASE)
        if email_match and re.match(r'[\w\.-]+@[\w\.-]+\.\w{2,}', email_match.group(1)):
            email = email_match.group(1).strip()
            break

    # Extract phone number
    phone_pattern = r'\+?\d{1,3}[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}|\d{10}'
    phone_numbers = re.findall(phone_pattern, text)[:1]  # Take the first phone number
    phone = phone_numbers[0] if phone_numbers else ''

    return name, email, phone

def generate_message(name):
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
        session_cookie = "your_quikr_session_cookie"  # Replace with your actual Quikr session cookie
        response = requests.get(url, headers=headers, cookies={'session': session_cookie})
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        candidates = []
        
        candidate_cards = soup.select('.shortlisted-candidate')  # Adjust selector based on actual HTML
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
        
        return candidates
    except Exception as e:
        print(f"Error scraping jobs: {str(e)}")
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
            return redirect(url_for('index'))
        else:
            error = 'Invalid username or password'
            return render_template('login.html', error=error)
    
    return render_template('login.html', error='')

@app.route('/find-teachers')
def find_teachers():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    candidates = scrape_teaching_jobs()
    return render_template('find_teachers.html', candidates=candidates)

@app.route('/', methods=['GET', 'POST'])
def index():
    if not session.get('logged_in'):
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
        # Handle PDF upload
        if 'resume' in request.files:
            file = request.files['resume']
            source = 'pdf'
            
            if file.filename == '':
                error = 'No file selected'
                return render_template('index.html', error=error, message=message, pdf_path=pdf_path, 
                                    whatsapp_number=whatsapp_number, contact_link=contact_link, source=source,
                                    name=name, email=email, phone=phone,
                                    fetched_name=fetched_name, fetched_email=fetched_email, fetched_phone=fetched_phone)
            
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                
                try:
                    file.save(filepath)
                    pdf_path = f"/Uploads/{filename}"
                    
                    with open(filepath, 'rb') as f:
                        pdf_reader = PyPDF2.PdfReader(f)
                        text = ''
                        for page in pdf_reader.pages:
                            text += page.extract_text() or ''
                    
                    fetched_name, fetched_email, fetched_phone = extract_info(text)
                    name = fetched_name
                    email = fetched_email
                    phone = fetched_phone
                    message = generate_message(name)
                    
                except Exception as e:
                    error = f"Failed to process PDF: {str(e)}"
        
        # Handle text input form
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
                else:
                    error = 'No valid phone number provided' if phone else 'No phone number provided'
                    contact_link = f"mailto:mymeedpss@gmail.com?subject=Job%20Application%20-%20{name}&body=Please%20attach%20your%20CV"
        
        else:
            error = 'No valid input provided'
            return render_template('index.html', error=error, message=message, pdf_path=pdf_path, 
                                whatsapp_number=whatsapp_number, contact_link=contact_link, source=source,
                                name=name, email=email, phone=phone,
                                fetched_name=fetched_name, fetched_email=fetched_email, fetched_phone=fetched_phone)
        
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
    return redirect(url_for('login'))

@app.route('/Uploads/<filename>')
def serve_uploaded_file(filename):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/cleanup', methods=['GET'])
def cleanup():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    file_path = request.args.get('file')
    if file_path:
        full_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(file_path))
        try:
            if os.path.exists(full_path):
                os.remove(full_path)
        except Exception as e:
            print(f"Failed to delete file: {str(e)}")
    return jsonify({"status": "success"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5700))
    app.run(host='0.0.0.0', port=port, debug=True)