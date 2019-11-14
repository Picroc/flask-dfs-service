''' flask app with mongo '''
from bson import ObjectId
import os
import json
import sys
import datetime
import random
from bson.objectid import ObjectId
from flask import Flask, request, jsonify
from flask_pymongo import PyMongo

from flask import Flask
from flask_cors import CORS

ROOT_PATH = os.environ.get('ROOT_PATH')

app = Flask(__name__)
CORS(app, origins='*')


@app.before_first_request
def init_all():
    data = mongo.db.dirs.find_one({'path': '/'})
    if data is None:
        mongo.db.dirs.insert_one({'path': '/', 'files': [], 'dirs': []})


def print_console(*message):
    print(*message, file=sys.stderr)


class JSONEncoder(json.JSONEncoder):
    def default(self, o):  # pylint: disable=method-hidden
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, datetime.datetime):
            return str(o)
        return json.JSONEncoder.default(self, o)


app.json_encoder = JSONEncoder


'''CONTROLLERS'''
@app.route('/init')
def init():
    mongo.db.drop_collection('dirs')
    mongo.db.drop_collection('files')
    init_all()
    return jsonify({'ok': True, 'message': 'Successfully reconstructed dfs'})


def recursive_dirs(root_path):
    root = mongo.db.dirs.find_one({'path': root_path})
    if root is None:
        return

    dirs = []
    files = []

    print_console(root)

    for directory in root['dirs']:
        recall = recursive_dirs(directory['dir_path'])
        print_console('Got', recall)
        if recall is not None:
            print_console('Adding', recall)
            dirs.append(recall)

    for file in root['files']:
        found_file = mongo.db.files.find_one({'_id': file['id']})
        if found_file is not None:
            files.append(found_file)

    return {'path': root_path, 'dirs': dirs, 'files': files}


def delete_cascade(root_path):
    root = mongo.db.dirs.find_one({'path': root_path})
    if root is None:
        return

    for directory in root['dirs']:
        delete_cascade(directory['dir_path'])

    for file in root['files']:
        mongo.db.files.delete_one({'_id': file['id']})

    mongo.db.dirs.delete_one({'_id': root['_id']})


def create_dir(name, to_insert):
    return {'path': to_insert + '/' + name if to_insert != '/' else to_insert + name, 'dirs': [], 'files': []}


def remove_dir_from_dir(to_update, name):
    rel_path = to_update['path'] + "/" + \
        name if to_update['path'] != '/' else '/' + name
    y = (i for i, v in enumerate(
        to_update['dirs']) if v['dir_path'] == rel_path)
    try:
        to_update['dirs'].pop(next(y))
    except:
        return None

    return to_update


@app.route('/dirs', methods=['GET', 'POST', 'DELETE'])
def dir():
    if request.method == 'GET':
        if request.args.get('path') is None:
            return jsonify({'ok': False, 'message': 'No path listed'}), 400

        db_response = recursive_dirs(request.args.get('path'))

        if db_response is None:
            return jsonify({'ok': False, 'message': 'No such directory'}), 400

        return jsonify(db_response)

    query_data = request.get_json()

    if request.method == 'POST':
        if query_data.get('dir') is None or query_data.get('name') is None:
            return jsonify({'ok': False, 'message': 'No name or path specified'}), 400

        to_insert = mongo.db.dirs.find_one({'path': query_data.get('dir')})
        if to_insert is None:
            return jsonify({'ok': False, 'message': 'No such directory'}), 400

        new_dir = create_dir(query_data.get('name'), to_insert['path'])
        print_console(new_dir)
        if mongo.db.dirs.find_one({'path': new_dir['path']}) is not None:
            return jsonify({'ok': False, 'message': 'This directory already exists'}), 400

        mongo.db.dirs.insert_one(new_dir)

        to_insert['dirs'].append({'dir_path': new_dir['path']})
        mongo.db.dirs.update({'_id': to_insert['_id']}, {
                             '$set': to_insert}, upsert=False)

        return jsonify({'ok': True, 'message': 'Successfully created dir'}), 200

    if request.method == 'DELETE':
        if query_data.get('dir') is None or query_data.get('name') is None:
            return jsonify({'ok': False, 'message': 'No path specified'}), 400

        to_update = mongo.db.dirs.find_one({'path': query_data.get('dir')})
        if to_update is None:
            return jsonify({'ok': False, 'message': 'No such directory'}), 400

        print_console('FOUND IS', to_update)
        to_update = remove_dir_from_dir(
            to_update, query_data.get('name'))
        print_console('NOW IS', to_update)
        mongo.db.dirs.update_one(
            {'_id': to_update['_id']}, {'$set': to_update})

        rel_path = query_data.get('dir') + '/' + query_data.get(
            'name') if query_data.get('dir') != '/' else '/' + query_data.get('name')
        delete_cascade(rel_path)
        return jsonify({'ok': True, 'message': 'Successfully removed dir'}), 200


def get_dir_and_file(path):
    sliced = path.split('/')

    directory = "/".join(sliced[:-1]) if sliced[:-1] != [''] else '/'
    file = sliced[-1]

    return directory, file


def remove_file_from_dir(to_update, name):
    y = (i for i, v in enumerate(to_update['files']) if v['name'] == name)
    try:
        to_update['files'].pop(next(y))
    except:
        return None

    return to_update


@app.route('/files', methods=['GET', 'POST', 'DELETE'])
def files():
    if request.method == 'GET':
        if request.args.get('path') is None:
            return jsonify({'ok': False, 'message': 'No path specified'}), 400

        dir_name, file_name = get_dir_and_file(request.args.get('path'))
        print_console('FILE NAME AND DIR', file_name, dir_name)
        req_file = mongo.db.files.find_one(
            {'dir': dir_name, 'name': file_name})

        if req_file is None:
            return jsonify({'ok': False, 'message': 'No such file or directory'}), 400

        return jsonify({'name': req_file['name'], 'dir': req_file['dir'], 'metadata': {'size': random.randint(0, 512), 'servers': [{'name': 'serv1'}, {'name': 'superkruto'}]}})

    query_data = request.get_json()

    if request.method == 'POST':
        if query_data.get('dir') is None or query_data.get('name') is None:
            return jsonify({'ok': False, 'message': 'No path or name specified'}), 400

        if mongo.db.files.find_one({'dir': query_data.get('dir'), 'name': query_data.get('name')}) is not None:
            return jsonify({'ok': False, 'message': 'File already exists'}), 400

        mongo.db.files.insert_one(
            {'dir': query_data.get('dir'), 'name': query_data.get('name')})

        new_file = mongo.db.files.find_one(
            {'dir': query_data.get('dir'), 'name': query_data.get('name')})

        to_update = mongo.db.dirs.find_one({'path': query_data.get('dir')})
        print_console('TO UPDATE', to_update)
        to_update['files'].append(
            {'name': query_data.get('name'), 'id': new_file['_id']})

        print_console('TO UPDATE', to_update)
        mongo.db.dirs.update({'_id': to_update['_id']}, {
            '$set': to_update}, upsert=False)
        return jsonify({'ok': True, 'message': 'File successfully created'}), 200

    if request.method == 'DELETE':
        if query_data.get('dir') is None or query_data.get('name') is None:
            return jsonify({'ok': False, 'message': 'No path or name specified'}), 400

        req_file = mongo.db.files.find_one(
            {'dir': query_data.get('dir'), 'name': query_data.get('name')})
        if req_file is None:
            return jsonify({'ok': False, 'message': 'No such file'}), 400

        to_update = mongo.db.dirs.find_one({'path': query_data.get('dir')})

        to_update = remove_file_from_dir(to_update, query_data.get('name'))
        mongo.db.dirs.update({'_id': to_update['_id']}, {
                             '$set': to_update}, upsert=False)

        mongo.db.files.delete_one({'_id': req_file['_id']})

        return jsonify({'ok': True, 'message': 'File removed'})


app.config['MONGO_URI'] = os.environ.get('DB')
mongo = PyMongo(app)
