import pytesseract
from PIL import Image

def extract_image_text(file_path):
    image = Image.open(file_path)
    
    text = pytesseract.image_to_string(image)
    
    return text