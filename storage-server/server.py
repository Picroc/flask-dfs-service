from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
import requests
import os
import sys
import shutil
import glob
from threading import Timer

app = Flask(__name__)

uploads = os.path.join('./', 'buffer')
NSNAME = os.environ.get('NSNAME')


def init():
    _, _, free = shutil.disk_usage('/')
    for file in glob.glob('buffer/*.*'):
        os.remove(file)
    try:
        res = requests.post('http://' + NSNAME + ':5000/join', json={
            'name': os.uname(),
            'space': free
        })
        print('Response from server: ', res.text, file=sys.stderr)
    except:
        print('Error occured', file=sys.stderr)
        s = Timer(5.0, init)
        s.start()


@app.route('/ping')
def pong():
    return 'PONG'


@app.route('/transaction', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        f = request.files.get('attach')
        f.save('buffer/' + secure_filename(f.filename))
        return jsonify({'ok': True, 'message': 'File received'}), 200

    if request.method == 'GET':
        filename = request.args.get('filename')
        if filename is None:
            return jsonify({'ok': False, 'message': 'No filename specified'}), 400

        print('Trying to find', filename, file=sys.stderr)

        try:
            return send_file('buffer/' + secure_filename(filename))
        except:
            return jsonify({'ok': False, 'message': 'No such file'}), 400


init()
