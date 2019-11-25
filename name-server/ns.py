''' flask app with mongo '''
from bson import ObjectId
import threading
import os
import json
import sys
import datetime
import random
from bson.objectid import ObjectId
from flask import Flask, request, jsonify, send_file, redirect
from flask_pymongo import PyMongo, ObjectId
import requests
from time import sleep
from shutil import copyfileobj

from flask import Flask
from flask_cors import CORS
from werkzeug.utils import secure_filename

ROOT_PATH = os.environ.get('ROOT_PATH')

app = Flask(__name__)
CORS(app, origins='*')


available_servers = []


def set_interval(func, sec):
    def func_wrapper():
        set_interval(func, sec)
        func()
    t = threading.Timer(sec, func_wrapper)
    t.start()
    return t


@app.before_first_request
def init_all():
    global available_servers
    data = mongo.db.dirs.find_one({'path': '/'})
    if data is None:
        mongo.db.dirs.insert_one({'path': '/', 'files': [], 'dirs': []})

    available_servers = []
    set_interval(check_connections, 10)


def check_connections():
    global available_servers
    disc_servers = []
    if available_servers == []:
        return
    for idx, server in enumerate(available_servers):
        try:
            pong_resp = requests.get('http://' + server['id'] + ':4000/ping')
            if pong_resp.text == 'PONG':
                print_console('Sever ', server['id'], ' is active!')
                sys.stderr.flush()
            else:
                print_console('Server ', server['id'], ' is not active!')
                # check_files_servers(server['id'])
                disc_servers.append(server['id'])
                sys.stderr.flush()
        except:
            print_console('Server ', server['id'], ' is not active!')
            # check_files_servers(server['id'])
            disc_servers.append(server['id'])
            available_servers[idx]['size'] = 0
            sys.stderr.flush()

    available_servers = [x for x in available_servers if x['size'] != 0]
    for server in disc_servers:
        check_files_servers(server)


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


@app.route('/')
def hello():
    return 'Hello from nameserver!'


'''STORAGE MANAGEMENT'''


def send_file_to_servers(filename, retries):
    if retries == 0:
        print_console('File ' + filename + ' failed to upload after retries.')
        return None

    file = open(filename, 'rb')
    file_size = os.path.getsize(filename)

    global available_servers
    if len(available_servers) < 2:
        print_console(
            'WARNING! Not enough servers available. Possible data loss')
        if available_servers == []:
            print_console('No server to send.')
            return
        random_servers = [available_servers[0]]
    else:
        random_servers = random.sample(available_servers, 2)

    try:
        for server in random_servers:
            resp = requests.post(
                'http://' + server['id'] + ':4000/transaction', files={'attach': file})
            if resp.json()['ok']:
                file.seek(0)
            else:
                return send_file_to_servers(filename, retries - 1)
    except:
        return send_file_to_servers(filename, retries - 1)

    return random_servers, file_size


def send_file_to_exact_servers(filename, server1, server2):
    file = open(str(filename), 'rb')

    global available_servers
    try:
        resp1 = requests.post(
            'http://' + server1 + ':4000/transaction', files={'attach': file})
        resp2 = requests.post(
            'http://' + server2 + ':4000/transaction', files={'attach': file})

        if resp1.json()['ok'] and resp2.json()['ok']:
            return True
        else:
            return False
    except:
        return False


def get_file_from_servers(file):
    try:
        print_console('Trying to get file from server 1')
        resp_file = requests.get(
            'http://' + file['servers'][0]['id'] + ':4000/transaction?filename=' + str(file['_id']))
        print_console('Got from storage server', resp_file)
        with open(str(file['_id']), 'wb') as f:
            print_console('Extracting file data')
            resp_file.raw.decode_content = True
            print_console('Copying file data')
            print_console(resp_file.content)
            f.write(resp_file.content)
            print_console('Done')
            f.close()
        return True
    except:
        try:
            print_console('Trying to get file from server 2')
            resp_file = requests.get(
                'http://' + file['servers'][1]['id'] + ':4000/transaction?filename=' + str(file['_id']))
            with open(str(file['_id']), 'wb') as f:
                print_console('Extracting file data')
                resp_file.raw.decode_content = True
                print_console('Copying file data')
                print_console(resp_file.content)
                f.write(resp_file.content)
                print_console('Done')
                f.close()
            return True
        except:
            print_console('Sorry mate')
            return False


def replicate(file):
    found = get_file_from_servers(file)
    if not found:
        print_console('Replication failed')
        return

    sent, file_size = send_file_to_servers(str(file['_id']), 3)
    if not sent:
        print_console('Replication failed')
        return

    file['servers'] = []
    for server in sent:
        file['servers'].append({
            'id': server['id']
        })

    mongo.db.files.update_one({'_id': file['_id']}, {'$set': file})

    print_console('Replication done!')


def replicate_copy(file, new_dir, new_name):
    new_id = ObjectId()
    found = get_file_from_servers(file)
    if not found:
        print_console('Replication failed')
        return

    os.rename(str(file['_id']), str(new_id))

    sent, file_size = send_file_to_servers(str(new_id), 3)
    if not sent:
        print_console('Replication failed')
        return

    file['servers'] = []
    for server in sent:
        file['servers'].append({
            'id': server['id']
        })

    file['_id'] = new_id

    file['dir'] = new_dir
    file['name'] = new_name

    mongo.db.files.insert_one(file)

    to_update = mongo.db.dirs.find_one({'path': new_dir})
    print_console('TO UPDATE', to_update)
    to_update['files'].append(
        {'name': new_name, 'id': new_id})

    print_console('TO UPDATE', to_update)
    mongo.db.dirs.update({'_id': to_update['_id']}, {
        '$set': to_update}, upsert=False)

    print_console('Replication done!')
    return True


def check_files_servers(disconnected_id):
    for found in mongo.db.files.find({"servers": {'id': disconnected_id}}):
        if len(available_servers) > 1:
            replicate(found)
        else:
            print_console('No servers to replicate!')

    print_console('DONE')


@app.route('/join', methods=['POST'])
def join():
    data = request.get_json()

    print_console('Got new storage server', data.get('name')[1], '!')

    global available_servers
    if ([x for x in available_servers if x['id'] == data.get('name')[1]]) == []:
        available_servers.append({
            'id': data.get('name')[1],
            'size': data.get('space')
        })

    print_console('Available now servers:', available_servers)
    return jsonify({'ok': True, 'message': 'Successfully added to servers'}), 200


'''CONTROLLERS'''
@app.route('/init')
def init():
    mongo.db.drop_collection('dirs')
    mongo.db.drop_collection('files')
    init_all()
    return jsonify({'ok': True, 'message': 'Successfully reconstructed dfs'}), 200


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


@app.route('/info')
def info():
    available_size = 0
    for server in available_servers:
        available_size += server['size']

    return jsonify({'available_space': available_size, 'servers': [x['id'] for x in available_servers]})


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

        return jsonify({'name': req_file['name'], 'dir': req_file['dir'], 'metadata': {'size': req_file['metadata']['size']}, 'servers': req_file['servers']})

    query_data = request.get_json()

    if request.method == 'POST':
        if query_data.get('dir') is None or query_data.get('name') is None:
            return jsonify({'ok': False, 'message': 'No path or name specified'}), 400

        if mongo.db.files.find_one({'dir': query_data.get('dir'), 'name': query_data.get('name')}) is not None:
            return jsonify({'ok': False, 'message': 'File already exists'}), 400

        mongo.db.files.insert_one(
            {'dir': query_data.get('dir'), 'name': query_data.get('name'), 'servers': [], 'metadata': {'size': 0}})

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


@app.route('/files/transaction', methods=['GET', 'POST'])
def transaction():
    if request.method == 'POST':
        if len(available_servers) == 0:
            return jsonify({'ok': False, 'message': 'No storage servers connected'}), 500

        file = request.files.get('attach')
        if file is None:
            return jsonify({'ok': False, 'message': 'File is not attached'}), 400

        if request.args.get('dir') is None or request.args.get('name') is None:
            return jsonify({'ok': False, 'message': 'No dir or file name specified'}), 400

        filepath = mongo.db.files.find_one(
            {'name': request.args.get('name'), 'dir': request.args.get('dir')})
        if filepath is None:
            return jsonify({'ok': False, 'message': 'No such file or directory'}), 400

        file.save(str(filepath['_id']))

        if len(filepath['servers']) == 2:
            sent = send_file_to_exact_servers(
                str(filepath['_id']), filepath['servers'][0]['id'], filepath['servers'][1]['id'])
            if sent:
                return jsonify({'ok': True, 'message': 'File successfully sent'}), 200

        sent, file_size = send_file_to_servers(str(filepath['_id']), 3)

        if sent is None:
            return jsonify({'ok': False, 'message': 'File was not sent, something went wrong on our side'}), 500

        filepath['servers'] = []
        for server in sent:
            filepath['servers'].append({
                'id': server['id']
            })

        filepath['metadata']['size'] = file_size

        mongo.db.files.update_one({'_id': filepath['_id']}, {'$set': filepath})

        return jsonify({'ok': True, 'message': 'File successfully sent'}), 200

    if request.method == 'GET':
        query_data = request.args
        if query_data.get('name') is None or query_data.get('dir') is None:
            return jsonify({'ok': False, 'message': 'No name or dir specified'}), 400

        filepath = mongo.db.files.find_one(
            {'dir': query_data.get('dir'), 'name': query_data.get('name')})
        if filepath is None:
            return jsonify({'ok': False, 'message': 'No such file or directory'})

        downloaded = get_file_from_servers(filepath)
        if downloaded:
            return send_file(str(filepath['_id']), attachment_filename=filepath['name'])
        else:
            return jsonify({'ok': False, 'message': 'Failed to download file'}), 500


@app.route('/files/move', methods=['POST'])
def files_move():
    query_data = request.get_json()

    if query_data.get('dir') is None or query_data.get('name') is None or query_data.get('dest') is None or query_data.get('dest_name') is None:
        return jsonify({'ok': False, 'message': 'No name or dir specified'}), 400

    current = mongo.db.files.find_one(
        {'dir': query_data.get('dir'), 'name': query_data.get('name')})

    if current is None:
        return jsonify({'ok': False, 'message': 'No such file or directory'}), 400

    current_dir = mongo.db.dirs.find_one({'path': query_data.get('dir')})
    dist = mongo.db.dirs.find_one({'path': query_data.get('dest')})

    if dist is None:
        return jsonify({'ok': False, 'message': 'Destination folder does not exist'}), 400

    if query_data.get('dir') == query_data.get('dest'):
        if query_data.get('name') == query_data.get('dest_name'):
            return jsonify({'ok': True, 'message': 'File was not changed'}), 200

    check_exists = mongo.db.files.find_one(
        {'dir': query_data.get('dest'), 'name': query_data.get('dest_name')})

    if check_exists is not None:
        return jsonify({'ok': False, 'message': 'File with that name already exists in destination derictory'}), 400

    if query_data.get('copy') is not None:
        done = replicate_copy(current, query_data.get(
            'dest'), query_data.get('dest_name'))
        if done is not None:
            return jsonify({'ok': True, 'message': 'File successfully copied'}), 200
        else:
            return jsonify({'ok': False, 'message': 'File was not copied, something went wrong on uor side'}), 500

    current['dir'] = query_data.get('dest')
    current['name'] = query_data.get('dest_name')

    current_dir['files'] = [x for x in current_dir['files']
                            if x['name'] != query_data.get('name')]
    dist['files'].append(
        {'name': query_data.get('dest_name'), 'id': current['_id']})

    mongo.db.files.update_one({'_id': current['_id']}, {'$set': current})
    mongo.db.dirs.update_one({'_id': current_dir['_id']}, {
                             '$set': current_dir})
    mongo.db.dirs.update_one({'_id': dist['_id']}, {'$set': dist})

    return jsonify({'ok': True, 'message': 'File successfully moved'}), 200


app.config['MONGO_URI'] = os.environ.get('DB')
mongo = PyMongo(app)
