def parse_pdf_text(text):
    data = {}
    
    lines = text.strip().split("\n")
    
    for line in lines:
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
            
    return data