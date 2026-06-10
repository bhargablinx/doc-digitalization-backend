def parse_ocr_text(text):
    lines = [
        line.strip()
        for line in text.split("\n")
        if line.strip()
    ]

    data = {}

    for i in range(0, len(lines), 2):

        if i + 1 < len(lines):

            key = lines[i]
            value = lines[i + 1]

            data[key] = value

    return data