import os
import re
import csv
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
from flask import Flask, request, render_template, redirect, url_for, send_file
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker  # Updated import for SQLAlchemy 2.0

# Flask Setup
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads/'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_default_secret_key')

# Database Setup
Base = declarative_base()
engine = create_engine('sqlite:///images.db')
Session = sessionmaker(bind=engine)
session = Session()

# Model to store image information, extracted text, and contacts
class ImageRecord(Base):
    __tablename__ = 'images'
    id = Column(Integer, primary_key=True)
    original_name = Column(String, nullable=False)
    renamed_name = Column(String, nullable=False)
    extracted_text = Column(String, nullable=True)
    contacts = Column(String, nullable=True)

# Create the database and tables if they don't exist
Base.metadata.create_all(engine)

# Function to preprocess and enhance the image before OCR
def preprocess_image(image_path):
    image = Image.open(image_path)
    image = image.convert("L")
    image = ImageEnhance.Contrast(image).enhance(2)
    image = ImageEnhance.Sharpness(image).enhance(2)
    return image

# Function to clean OCR text for better extraction accuracy
def clean_text(text):
    text = re.sub(r'[^\w\s+]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text

# Function to format phone numbers without adding country code
def format_phone_number(phone):
    phone = re.sub(r'[^\d]', '', phone)  # Remove all non-digit characters
    if len(phone) > 10:
        formatted_phone = re.sub(r'(\d{3})(\d{3})(\d{4})$', r'\1 \2 \3', phone)
    else:
        formatted_phone = re.sub(r'(\d{5})(\d{5})', r'\1 \2', phone)
    return formatted_phone

# Function to extract phone numbers from text and format them
def extract_phone_numbers_from_text(text):
    cleaned_text = clean_text(text)
    phone_pattern = r'\b(?:\+?\d{1,3})?[-.\s]?\(?\d{2,4}?\)?[-.\s]?\d{2,4}[-.\s]?\d{2,4}[-.\s]?\d{2,4}\b'
    potential_phones = re.findall(phone_pattern, cleaned_text)
    unique_phones = list(set(potential_phones))

    formatted_phones = [format_phone_number(phone) for phone in unique_phones]
    return formatted_phones

# Function to process a single image and extract text and contacts
def process_single_image(image_path):
    processed_image = preprocess_image(image_path)
    extracted_text = pytesseract.image_to_string(processed_image, config='--oem 3 --psm 6')
    phone_numbers = extract_phone_numbers_from_text(extracted_text)
    contacts_text = ", ".join(phone_numbers) if phone_numbers else "No contacts found"
    return extracted_text, phone_numbers

# Function to clean up all files and database entries after download
def cleanup():
    # Delete all records from the database
    session.query(ImageRecord).delete()
    session.commit()
    
    # Remove all images in the upload folder
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.isfile(file_path):
            os.remove(file_path)

    # Remove the CSV file
    csv_file = 'extracted_contacts.csv'
    if os.path.exists(csv_file):
        os.remove(csv_file)

# Route to display the upload form with an input field for the base name
@app.route('/')
def upload_form():
    return render_template('upload.html')

# Route to handle multiple image uploads and generate a CSV file with contacts
@app.route('/', methods=['POST'])
def upload_images():
    base_name = request.form.get('base_name')  # Get the base name from the form input
    files = request.files.getlist('images')
    if not files or files[0].filename == '':
        return "No files selected"

    all_contacts = []
    uploaded_files = []

    for file in files[:100]:  # Limit to 100 images
        original_name = secure_filename(file.filename)
        renamed_name = f"img_{original_name}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], renamed_name)

        file.save(file_path)
        
        extracted_text, phone_numbers = process_single_image(file_path)
        all_contacts.extend(phone_numbers)  # Add contacts from this image to the list

        new_image = ImageRecord(
            original_name=original_name,
            renamed_name=renamed_name,
            extracted_text=extracted_text,
            contacts=", ".join(phone_numbers)
        )
        session.add(new_image)
        session.commit()

        uploaded_files.append(new_image)

    # Generate CSV with all contacts
    csv_filename = 'extracted_contacts.csv'
    with open(csv_filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Name", "", "Phone"])  # "Name" header in A, "Phone" in C
        for i, contact in enumerate(set(all_contacts), start=1):  # Add incremental number to base name
            writer.writerow([f"{base_name} {i}", "", f"+ {contact}"])  # Name in A, phone in C

    return redirect(url_for('show_results', csv_file=csv_filename))

# Route to show results of all uploaded images
@app.route('/results')
def show_results():
    images = session.query(ImageRecord).all()
    csv_file = request.args.get('csv_file', None)
    return render_template('results.html', images=images, csv_file=csv_file)

# Route to download the generated CSV file and clean up
@app.route('/download/<csv_file>')
def download_csv(csv_file):
    if os.path.exists(csv_file):
        response = send_file(csv_file, as_attachment=True)
        cleanup()  # Call the cleanup function after serving the CSV file
        return response
    else:
        return "CSV file not found", 404

if __name__ == "__main__":
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    port = int(os.environ.get("PORT", 5000))  # Use PORT from environment, default to 5000
    app.run(host="0.0.0.0", port=port, debug=False)  # Use production settings
import os
import re
import csv
import pytesseract
from PIL import Image, ImageEnhance
from flask import Flask, request, render_template, redirect, url_for, send_file
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine, Column, Integer, String, inspect
from sqlalchemy.orm import declarative_base, sessionmaker

# Flask Setup
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads/'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_default_secret_key')

# Database Setup
Base = declarative_base()
engine = create_engine('sqlite:///images.db')
Session = sessionmaker(bind=engine)
session = Session()

# Model to store image information, extracted text, and contacts
class ImageRecord(Base):
    __tablename__ = 'images'
    id = Column(Integer, primary_key=True)
    original_name = Column(String, nullable=False)
    renamed_name = Column(String, nullable=False)
    extracted_text = Column(String, nullable=True)
    contacts = Column(String, nullable=True)

# Create the database and tables if they don't exist
if not inspect(engine).has_table("images"):
    Base.metadata.create_all(engine)

# Function to preprocess and enhance the image before OCR
def preprocess_image(image_path):
    image = Image.open(image_path)
    image = image.convert("L")  # Convert to grayscale
    image = ImageEnhance.Contrast(image).enhance(2)  # Increase contrast
    image = ImageEnhance.Sharpness(image).enhance(2)  # Sharpen the image
    return image

# Function to clean OCR text for better extraction accuracy
def clean_text(text):
    text = re.sub(r'[^\w\s+]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text

# Function to format phone numbers without adding country code
def format_phone_number(phone):
    phone = re.sub(r'[^\d]', '', phone)
    if len(phone) > 10:
        formatted_phone = re.sub(r'(\d{3})(\d{3})(\d{4})$', r'\1 \2 \3', phone)
    else:
        formatted_phone = re.sub(r'(\d{5})(\d{5})', r'\1 \2', phone)
    return formatted_phone

# Function to extract phone numbers from text and format them
def extract_phone_numbers_from_text(text):
    cleaned_text = clean_text(text)
    phone_pattern = r'\b(?:\+?\d{1,3})?[-.\s]?\(?\d{2,4}?\)?[-.\s]?\d{2,4}[-.\s]?\d{2,4}[-.\s]?\d{2,4}\b'
    potential_phones = re.findall(phone_pattern, cleaned_text)
    unique_phones = list(set(potential_phones))

    formatted_phones = [format_phone_number(phone) for phone in unique_phones]
    return formatted_phones

# Function to process a single image and extract text and contacts
def process_single_image(image_path):
    processed_image = preprocess_image(image_path)
    extracted_text = pytesseract.image_to_string(processed_image, config='--oem 3 --psm 6')
    phone_numbers = extract_phone_numbers_from_text(extracted_text)
    contacts_text = ", ".join(phone_numbers) if phone_numbers else "No contacts found"
    return extracted_text, phone_numbers

# Function to clean up all files and database entries after download
def cleanup():
    # Delete all records from the database
    session.query(ImageRecord).delete()
    session.commit()
    
    # Remove all images in the upload folder
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.isfile(file_path):
            os.remove(file_path)

    # Remove the CSV file
    csv_file = 'extracted_contacts.csv'
    if os.path.exists(csv_file):
        os.remove(csv_file)

# Route to display the upload form with an input field for the base name
@app.route('/')
def upload_form():
    return render_template('upload.html')

# Route to handle multiple image uploads and generate a CSV file with contacts
@app.route('/', methods=['POST'])
def upload_images():
    base_name = request.form.get('base_name')  # Get the base name from the form input
    files = request.files.getlist('images')
    if not files or files[0].filename == '':
        return "No files selected"

    all_contacts = []
    uploaded_files = []

    for file in files[:100]:  # Limit to 100 images
        original_name = secure_filename(file.filename)
        renamed_name = f"img_{original_name}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], renamed_name)

        file.save(file_path)
        
        extracted_text, phone_numbers = process_single_image(file_path)
        all_contacts.extend(phone_numbers)

        new_image = ImageRecord(
            original_name=original_name,
            renamed_name=renamed_name,
            extracted_text=extracted_text,
            contacts=", ".join(phone_numbers)
        )
        session.add(new_image)
        session.commit()

        uploaded_files.append(new_image)

    # Generate CSV with all contacts
    csv_filename = 'extracted_contacts.csv'
    with open(csv_filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Name", "", "Phone"])
        for i, contact in enumerate(set(all_contacts), start=1):
            writer.writerow([f"{base_name} {i}", "", f"+ {contact}"])

    return redirect(url_for('show_results', csv_file=csv_filename))

# Route to show results of all uploaded images
@app.route('/results')
def show_results():
    images = session.query(ImageRecord).all()
    csv_file = request.args.get('csv_file', None)
    return render_template('results.html', images=images, csv_file=csv_file)

# Route to download the generated CSV file and clean up
@app.route('/download/<csv_file>')
def download_csv(csv_file):
    if os.path.exists(csv_file):
        response = send_file(csv_file, as_attachment=True)
        cleanup()
        return response
    else:
        return "CSV file not found", 404

if __name__ == "__main__":
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
