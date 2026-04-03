import pytesseract
import mss
import cv2
import numpy as np

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

with mss.mss() as sct:

    monitor = {"top": 300, "left": 300, "width": 600, "height": 200}

    img = np.array(sct.grab(monitor))

    gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)

    text = pytesseract.image_to_string(gray, lang="chi_sim")

    print(text)