from PIL import ImageFont, Image, ImageDraw, ImageOps
from PyPDF2 import PdfFileReader, PdfFileWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from flask import Flask, request
from google.cloud import storage
import base64
import json
import zlib
import io
import re
import os

app = Flask(__name__)

def handwriting_gen_file(text, size, deg, height_add=0, reverse=False):
    storage.Client().bucket('singularity-beta').blob('pdf-gen/Cursive.ttf').download_to_filename('Cursive.ttf')
    font = ImageFont.truetype('Cursive.ttf', size)
    fontimage = Image.new('L', (font.getsize(re.sub(r'[–—]', '-', re.sub(r'[«»“”]', '"', '  '.join(text.split()))))[0], sum(font.getmetrics()) - 20 + height_add))
    ImageDraw.Draw(fontimage).text((0, 0), text, fill=255, font=font)

    if reverse:
        return fontimage.rotate(deg, expand=True)

    ImageOps.invert(fontimage.rotate(deg, expand=True)).save(f'./{text}.png', 'PNG')
    os.remove('Cursive.ttf')


@app.route("/", methods=['POST'])
def pdf_gen():
    pdf_bytes = zlib.decompress(base64.b64decode(request.form['pdf_zip']))
    draw_items = json.loads(request.form['draw_items'])

    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)

    for draw_item in draw_items:

        text = draw_item['text']

        if draw_item['is_usd']:
            text = str.rjust(str('${:,.2f}'.format(int(text))), 7)

        if draw_item['font_name'] == 'Handwritten':
            handwriting_gen_file(text, draw_item['font_size'], draw_item['hand_font_deg'], draw_item['hand_height_shift'], reverse=False)
            can.drawImage(f'./{text}.png', draw_item['x'], draw_item['y'])
            os.remove(f'./{text}.png')

        else:
            can.setFont(draw_item['font_name'], draw_item['font_size'])
            can.drawString(draw_item['x'], draw_item['y'], text)

    can.save()
    packet.seek(0)

    # create pdf sent over wire
    blank_pdf = './blank.pdf'
    blank_pdf_handle = open(blank_pdf, 'wb')
    blank_pdf_handle.write(pdf_bytes)
    blank_pdf_handle.close()

    # write content to pdf
    page = PdfFileReader(open(blank_pdf, 'rb')).getPage(0)
    page.mergePage(PdfFileReader(packet).getPage(0))
    output = PdfFileWriter()
    output.addPage(page)

    # read and return new, written pdf
    tmp = io.BytesIO()
    output.write(tmp)
    os.remove(blank_pdf)
    return base64.b64encode(zlib.compress(tmp.getvalue(), 9))


if __name__ == '__main__':
    server_port = os.environ.get('PORT', '8080')
    app.run(debug=False, port=server_port, host='0.0.0.0')