import argparse
import base64
import collections
import errno
import glob
import io
import os
import os.path
import pathlib
import shutil
import tempfile
from os.path import basename, join
import traceback
from dotenv import load_dotenv

import cv2
import ray
import zxing
from Crypto.Cipher import AES
from pdf2image import convert_from_path
from PIL import Image
from PyPDF2 import PdfFileReader
from PyPDF2.pdf import PdfFileWriter
from reportlab.pdfgen import canvas

load_dotenv()

ray.init(include_dashboard=False, _redis_password=None)

# 128, 192, or 256 bits
key = os.environ.get("KEY")
assert(len(key) in {16, 24, 32})
key = str.encode(key)


# Taken from https://stackoverflow.com/a/600612/119527


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def safe_open_w(path):
    ''' Open "path" for writing, creating any parent directories as needed.
    '''
    mkdir_p(os.path.dirname(path))
    return open(path, 'wb')


def decryptCode(ctext):
    try:
        # seperate them by ;
        params = ctext.split(";")
        cipher = AES.new(key, AES.MODE_EAX,
                         nonce=base64.b64decode(str.encode(params[0])))
        plaintext = cipher.decrypt(base64.b64decode(str.encode(params[1])))
        # verify validity
        try:
            cipher.verify(base64.b64decode(str.encode(params[2])))
            print("The message is authentic:", plaintext.decode("utf-8"))
            return True, plaintext.decode("utf-8")
        except ValueError:
            print("Key incorrect or message corrupted")
            return False, "Code is invalid or corrupted"
    except:
        print("Invalid code")
        return False, "Code is invalid"


@ray.remote
def processFile(file, input_folder, output_folder):
    returnData = None
    attempt = 0
    isPDF = False
    # convert pdf file to png
    # scan the image and verify
    file_name = basename(file)
    try:
        with tempfile.TemporaryDirectory() as path:
            # check if pdf
            images_from_path = []
            if (pathlib.Path(file).suffix.lower() == ".pdf"):
                images_from_path = convert_from_path(
                    file, output_folder=path, fmt="jpeg", thread_count=4, dpi=400, paths_only=True)
                isPDF = True
            else:
                images_from_path = [file]

            for image in images_from_path:
                image_filename = os.path.splitext(image)[0]

                # modify contrast
                im = Image.open(image)
                thresh = 100
                def fn(x): return 255 if x > thresh else 0
                r = im.convert('L').point(fn, mode='1')
                fd1, image_mth = tempfile.mkstemp(suffix=".jpg")
                r.save(image_mth)

                img = cv2.imread(image)
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                res = cv2.adaptiveThreshold(
                    gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 127, 10)
                #cv2.imshow("text", res)
                # cv2.waitKey(0)
                fd2, image_cv2 = tempfile.mkstemp(suffix=".jpg")
                cv2.imwrite(image_cv2, res)
                #input("press to continue")

                # im.save(image)
                #decoded = decode(image)
                reader = zxing.BarCodeReader()
                print("Decoding:", file_name)
                decoded = [
                    reader.decode(image, try_harder=True,
                                  possible_formats="QR_CODE"),
                    reader.decode(image_mth, try_harder=True,
                                  possible_formats="QR_CODE"),
                    reader.decode(image_cv2, try_harder=True,
                                  possible_formats="QR_CODE")
                ]
                # close them all
                os.close(fd1)
                os.close(fd2)
                # read pdf file
                pdf = None
                if isPDF:
                    pdf = PdfFileReader(file, strict=False)
                else:
                    # create PDF out of this crap
                    with tempfile.TemporaryDirectory() as tmp:
                        path = os.path.join(
                            tmp, os.path.relpath(file, input_folder))
                        path = os.path.splitext(path)[0] + ".pdf"
                        pathlib.Path(os.path.dirname(path)).mkdir(
                            parents=True, exist_ok=True)
                        Image.open(file).convert("RGB").save(path)
                        print("Converted image to", path)
                        pdf = PdfFileReader(path, strict=False)

                # catch invalid QR codes
                success, data = None, None
                qrData = None
                for decodeData in decoded:
                    if not (decodeData == None or decodeData.raw == ""):
                        qrData = decodeData.raw
                        break
                if qrData == None:
                    success, data = False, "Could not find QR Code automatically."
                    print(file_name, "- NOT FOUND")
                    returnData = (1, os.path.relpath(file, input_folder))
                else:
                    d = qrData
                    print(file_name, d)
                    success, data = decryptCode(d.strip())

                if success:
                    # add to dictionary, mention if possible duplicate
                    returnData = (data, os.path.relpath(file, input_folder))
                    # summary[data].append(file_name)
                    # if len(summary[data]) > 1:
                    #    print("WARNING: Reuse of", data)
                else:
                    if success == None or success == False:
                        returnData = (2, os.path.relpath(file, input_folder))
                        if qrData == None:
                            returnData = (
                                1, os.path.relpath(file, input_folder))
                            attempt += 1
                            if attempt < pdf.getNumPages():
                                continue
                        #invalidCode += 1

                packet = io.BytesIO()
                originalMediabox = pdf.getPage(0).mediaBox
                firstPageWidth = originalMediabox.getWidth()
                firstPageHeight = originalMediabox.getHeight()
                can = canvas.Canvas(
                    packet, pagesize=[firstPageWidth, firstPageHeight])

                # to make text scale with nasty pdf sizes
                textMultiplier = float(firstPageWidth) / 600

                can.setFont("Helvetica", 12*textMultiplier)
                # draw verification info
                can.drawString(10, float(firstPageHeight) -
                               10 - (12*textMultiplier), "Verification Info:")
                if success == False:
                    can.setFillColorRGB(0.8, 0, 0)
                else:
                    can.setFillColorRGB(0, 0.6, 0)
                can.setFont("Helvetica", 10*textMultiplier)
                can.drawString(10, float(firstPageHeight) -
                               10 - (24*textMultiplier), data)
                can.save()

                # move to the beginning of the StringIO buffer
                packet.seek(0)
                new_pdf = PdfFileReader(packet, strict=False)
                # read your existing PDF
                existing_pdf = pdf
                output = PdfFileWriter()
                # add the "watermark" (which is the new pdf) on the existing page
                page = existing_pdf.getPage(0)
                page.mergePage(new_pdf.getPage(0))
                output.addPage(page)
                # finally, write "output" to a real file
                outputStream = safe_open_w(
                    join(output_folder, os.path.relpath(str(pathlib.Path(file).with_suffix(".pdf")), input_folder)))
                output.write(outputStream)
                outputStream.close()

                break

                # if data != False:
                #     # move the file
                #     new_name = data
                #     new_name = '{}.pdf'.format(new_name)
                #     print('new name: ', new_name)
                #     copyfile(file, join(output_folder, new_name))
    except Exception as e:
        print("Error: ", file_name)
        print("Error is :", repr(e))
        traceback.print_tb(e.__traceback__)
        return (3, os.path.relpath(file, input_folder))
    return returnData


def cihan(input_folder, output_folder):
    # save a dictionary for duplicate detection
    summary = collections.defaultdict(list)
    notFound = []
    invalidCode = []
    weirdErrors = []

    refs = []
    files = glob.glob(join(input_folder, '**/*.png'), recursive=True) + \
        glob.glob(join(input_folder, '**/*.jpg'), recursive=True) + \
        glob.glob(join(input_folder, '**/*.jpeg'), recursive=True) + \
        glob.glob(join(input_folder, '**/*.pdf'), recursive=True)
    for file in (files):
        ref = processFile.remote(file, input_folder, output_folder)
        refs.append(ref)

    results = ray.get(refs)

    for result in results:
        data, file_name = result
        if data == 1:
            notFound.append(file_name)
        elif data == 2:
            invalidCode.append(file_name)
        elif data == 3:
            weirdErrors.append(file_name)
        else:
            summary[data].append(file_name)
            if len(summary[data]) > 1:
                print("WARNING: Reuse of", data)
    # put summaries into a file
    with open("codeused.txt", "w", encoding='utf8') as output:
        for item in summary:
            output.write(item)
            output.write("\n")
        output.close()
    with open("notfound.txt", "w", encoding='utf8') as output:
        for item in notFound:
            output.write(item)
            output.write("\n")
        output.close()
    with open("invalidcode.txt", "w", encoding='utf8') as output:
        for item in invalidCode:
            output.write(item)
            output.write("\n")
        output.close()
    with open("weirdErrors.txt", "w", encoding='utf8') as output:
        for item in weirdErrors:
            output.write(item)
            output.write("\n")
        output.close()

    # go through all files again, edit the ones that are potentially duplicate
    print("---- Summary ----")
    print("Processed:", len(summary))
    print("Cannot find QR Code:", len(notFound))
    print("Invalid QR Code:",  len(invalidCode))
    print("Weird Characters in QR Code (or errors):",  len(weirdErrors))

    with open("codemaps.txt", "w", encoding='utf8') as codemap:
        with open("dupes.txt", "w", encoding='utf8') as dupefile:
            for dupe in summary:
                dupecount = len(summary[dupe])
                codemap.write("------- ")
                codemap.write(dupe)
                codemap.write("\n")
                for file_name in summary[dupe]:
                    codemap.write(file_name)
                    codemap.write("\n")
                if dupecount > 1:

                    print("Duplicate:", dupe)
                    dupefile.write("------- ")
                    dupefile.write(dupe)
                    dupefile.write("\n")

                    # reused?
                    for file_name in summary[dupe]:
                        file_name = str(pathlib.Path(
                            file_name).with_suffix(".pdf"))
                        file = join(output_folder, file_name)
                        dupefile.write(file_name)
                        dupefile.write("\n")
                        pdf = PdfFileReader(file)
                        packet = io.BytesIO()
                        originalMediabox = pdf.getPage(0).mediaBox
                        firstPageWidth = originalMediabox.getWidth()
                        firstPageHeight = originalMediabox.getHeight()
                        can = canvas.Canvas(
                            packet, pagesize=[firstPageWidth, firstPageHeight])

                        # to make text scale with nasty pdf sizes
                        textMultiplier = float(firstPageWidth) / 600
                        can.setFillColorRGB(0.8, 0, 0)
                        can.setFont("Helvetica", 10*textMultiplier)
                        can.drawString(10, float(firstPageHeight) -
                                       10 - (36*textMultiplier), "CODE REUSED "+str(dupecount)+" TIMES")
                        can.save()

                        # move to the beginning of the StringIO buffer
                        packet.seek(0)
                        new_pdf = PdfFileReader(packet)
                        # read your existing PDF
                        existing_pdf = PdfFileReader(open(file, "rb"))
                        output = PdfFileWriter()
                        # add the "watermark" (which is the new pdf) on the existing page
                        page = existing_pdf.getPage(0)
                        page.mergePage(new_pdf.getPage(0))
                        output.addPage(page)
                        # finally, write "output" to a temp file and overwrite the real file afterwards
                        outputStream = safe_open_w(join("tmp", file_name))
                        output.write(outputStream)
                        outputStream.close()

                        shutil.copy(join("tmp", file_name),
                                    join(output_folder, file_name))
                        os.remove(join("tmp", file_name))

                        # close file after done writing
                        # outputStream.close()
            dupefile.close()
        codemap.close()


def get_args():
    parser = argparse.ArgumentParser(description='Scan pdfs and rename them according to '
                                                 'data in barcodes they contain.'
                                                 '\nTested on python 3.6.'
                                                 '\nRequirements: pip install pdf2image pyzbar image pandas xlrd')
    parser.add_argument('-i', '--input_folder', default="test_subjects",
                        help='Where all pdf files take place.')
    parser.add_argument('-o', '--output_folder', default="out",
                        help='Where to copy new renamed pdf files.')
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    args = get_args()
    # create dirs if not exist
    if not os.path.exists(args.output_folder):
        os.makedirs(args.output_folder)
    if not os.path.exists("tmp"):
        os.makedirs("tmp")
    cihan(args.input_folder, args.output_folder)
