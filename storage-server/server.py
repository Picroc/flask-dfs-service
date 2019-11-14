from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import os
import sys

# ROOT_PATH = os.environ.get('ROOT_PATH')

app = Flask(__name__)

uploads = os.path.join('./', 'buffer')


@app.route('/upload', methods=['POST'])
def upload_file():
    if request.method == 'POST':
        # print(request.files.to_dict(), file=sys.stderr)

        f = request.files.get('attach')
        f.save(uploads + '/' + secure_filename(f.filename))
        return 'NOICE'
