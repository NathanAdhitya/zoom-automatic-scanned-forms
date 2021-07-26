This repository is not actively maintained. This is just a dump for one of my latest projects.

Since this was a quick project, I did not really bother to take notes of the entire environemnt, this is a rough list:
- Python 3.9
- ray 1.4.1
- Pillow 8.2.0
- zxing 0.12
- opencv-python 4.5.2.54
- pdf2image 1.16.0
- PyPDF2 1.26.0
- redis 3.5.3


Intention of this project:
1. Automatically send private messages to everyone in a zoom meeting a unique string tied to their zoom name. Upon a call of a function. `zoom.py` (This is done automatically by Selenium, and the string is an base64-encoded AES cipher from their zoom names.)
2. Individuals enter the codes inside of a website `id.html`, which produces a PDF file from `master-r1.pdf` (not included) with a QR code attached on the top left.
3. Individuals print, fill the form by hand, scan, then upload the form back to some other method that's not covered here.
4. All files are then collected into a folder. Using the program `verify.py`, the first page of all pdfs / image is scanned for QR Codes. Data embedded in the encrypted QR code are then used to verify the integrity of those who have submitted the file. The script will also output some files e.g. notfound.txt listing all files of which QR codes were not able to be found.
5. The results of the file are placed in the output folder (in PDF form). A text will appear in the top left corner indicating the status of the decrpyted content (success/fail) and the results (success: the decrypted contents, fail: fail message), along with potential issues in the next line e.g. duplicates found.