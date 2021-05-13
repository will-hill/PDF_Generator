from PIL import ImageFont, Image, ImageDraw, ImageOps
from PyPDF2 import PdfFileReader, PdfFileWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from google.cloud import bigquery
from flask import Flask, request, send_file
from google.cloud import storage
import base64
import json
import zlib
import io
import re
import os

app = Flask(__name__)


def handwriting_gen_file(text, size, deg, height_add=0, reverse=False):
    font = ImageFont.truetype('Cursive.ttf', size)
    fontimage = Image.new('L', (font.getsize(re.sub(r'[–—]', '-', re.sub(r'[«»“”]', '"', '  '.join(text.split()))))[0], sum(font.getmetrics()) - 20 + height_add))
    ImageDraw.Draw(fontimage).text((0, 0), text, fill=255, font=font)

    if reverse:
        return fontimage.rotate(deg, expand=True)

    ImageOps.invert(fontimage.rotate(deg, expand=True)).save(f'./{text}.png', 'PNG')


def sheets_to_bq(sheets_url, project_id, dataset_id, table_id, schema):
    bq_client = bigquery.Client()
    dataset = bq_client.create_dataset(bigquery.Dataset(f'{project_id}.{dataset_id}'), timeout=30, exists_ok=True)
    bq_client.delete_table(f'{project_id}.{dataset_id}.{table_id}', not_found_ok=True)

    table = bigquery.Table(dataset.table('inputs'), schema=schema)

    external_config = bigquery.ExternalConfig(bigquery.ExternalSourceFormat.GOOGLE_SHEETS)
    external_config.source_uris = [sheets_url]
    external_config.options.skip_leading_rows = 1
    external_config.options.range = ('Sheet1')
    external_config.autodetect = True
    external_config.schema = schema

    table = bq_client.create_table(table, exists_ok=True)

    draw_items = bq_client.query(f'SELECT * FROM {table.dataset_id}.{table.table_id}').to_dataframe().to_dict('records')

    return draw_items


@app.route("/generate-pdf", methods=['GET'])
def generate_pdf():
    print('START:GET - generate-pdf')

    project_id = request.args.get('project-id')
    sheets_url = request.args.get('sheet')
    dataset_id = request.args.get('dataset')
    table_id = request.args.get('table')
    gcs_pdf_url = request.args.get('pdf')

    schema = [bigquery.SchemaField('text', 'String'),
              bigquery.SchemaField('x', 'Integer'),
              bigquery.SchemaField('y', 'Integer'),
              bigquery.SchemaField('font_name', 'String'),
              bigquery.SchemaField('font_size', 'Integer'),
              bigquery.SchemaField('hand_font_deg', 'Integer'),
              bigquery.SchemaField('hand_height_shift', 'Integer'),
              bigquery.SchemaField('is_usd', 'Boolean')]

    print('query Sheets')
    draw_items = sheets_to_bq(sheets_url, project_id, dataset_id, table_id, schema)

    print('grab blank PDF')
    with open('blank.pdf') as blank_pdf:
        gcs_client = storage.Client()
        gcs_client.download_blob_to_file(gcs_pdf_url, blank_pdf)

    print('generate PDF')
    written_pdf = write_pdf(draw_items, 'blank.pdf')
    os.remove('blank.pdf')

    print('return PDF')
    return send_file(written_pdf)


def write_pdf(draw_items, blank_pdf):
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

    page = PdfFileReader(open(blank_pdf, 'rb')).getPage(0)
    page.mergePage(PdfFileReader(packet).getPage(0))
    output = PdfFileWriter()
    output.addPage(page)

    with open('written.pdf', 'wb') as written_pdf:
        output.write(written_pdf)

    return 'written.pdf'


@app.route("/", methods=['POST'])
def pdf_gen():
    print('START - pdf')
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


@app.route('/hello')
def hello():
    print('START - hello')

    return 'hello there\n'


if __name__ == '__main__':
    server_port = os.environ.get('PORT', '8080')
    app.run(debug=False, port=server_port, host='0.0.0.0')
