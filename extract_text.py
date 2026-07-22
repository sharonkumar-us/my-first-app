import pdfplumber
from docx import Document
import pdfplumber
from docx import Document
from pdf2image import convert_from_path
import pytesseract
import requests
from bs4 import BeautifulSoup
import os
import re

# --- Extract from benefits.pdf using pdfplumber ---
benefits_text = ""
with pdfplumber.open("source_docs/benefits.pdf") as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if text:
            benefits_text += text + "\n"

print("=== benefits.pdf extracted text (first 300 chars) ===")
print(benefits_text[:300])

# --- Extract from claims_process.docx using python-docx ---
doc = Document("source_docs/claims_process.docx")
claims_text = ""
for paragraph in doc.paragraphs:
    if paragraph.text.strip():
        claims_text += paragraph.text + "\n"

print("\n=== claims_process.docx extracted text (first 300 chars) ===")
print(claims_text[:300])

print("\nExtraction complete for both documents.")
from pdf2image import convert_from_path
import pytesseract

# --- OCR the scanned enrollment form ---
print("\n=== enrollment_scan.pdf OCR extraction ===")
pages = convert_from_path("source_docs/enrollment_scan.pdf")

enrollment_text = ""
for i, page_image in enumerate(pages):
    page_text = pytesseract.image_to_string(page_image)
    enrollment_text += page_text + "\n"
    print(f"--- Page {i+1} OCR output ---")
    print(page_text)

print("\nOCR extraction complete.")
import requests
from bs4 import BeautifulSoup

# --- Scrape public FAQ page ---
print("\n=== Scraping healthcare.gov FAQ page ===")
url = "https://www.healthcare.gov/get-answers/"
response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})

soup = BeautifulSoup(response.text, "html.parser")
main_content = soup.find("main")

if main_content:
    faq_text = main_content.get_text(separator=" ", strip=True)
else:
    faq_text = ""

print(faq_text[:500])
print(f"\nTotal characters extracted: {len(faq_text)}")
def clean_text(text):
    text = text.replace("â€™", "'").replace("â€œ", '"').replace("â€", '"')
    text = text.replace("â", "'")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

os.makedirs("raw_text", exist_ok=True)

with open("raw_text/benefits.txt", "w", encoding="utf-8") as f:
    f.write(clean_text(benefits_text))

with open("raw_text/claims_process.txt", "w", encoding="utf-8") as f:
    f.write(clean_text(claims_text))

with open("raw_text/enrollment.txt", "w", encoding="utf-8") as f:
    f.write(clean_text(enrollment_text))

with open("raw_text/faq.txt", "w", encoding="utf-8") as f:
    f.write(clean_text(faq_text))

print("\nAll cleaned text files saved to raw_text/")