import os
import sys
from flask import jsonify, request, make_response, send_from_directory

from ns import app

PORT = os.environ.get('PORT')
@app.route('/')
def index():
    return 'Hello from nameserver!'


if __name__ == '__main__':
    app.config['DEBUG'] = os.environ.get(
        'ENV') == 'development'  # Debug mode if development env
    app.run(host='0.0.0.0', port=int(PORT))  # Run the app
