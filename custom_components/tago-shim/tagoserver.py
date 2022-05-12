from flask import Flask, request, stream_with_context, jsonify, send_from_directory
from flask_cors import CORS
import threading
import time
import json
from .tagoapi import TagoApi
from .tagonet import TagoEvents
from SimpleWebSocketServer import WebSocket, SimpleWebSocketServer
import uuid
import logging
import threading

class TagoEventServer(SimpleWebSocketServer):
    clients = set()

    class EventHandler (WebSocket):
        def __init__(self, server, sock, address):
            super().__init__(server, sock, address)
            self.clients = TagoEventServer.clients

        def handleMessage(self):
            pass
            
        def handleConnected(self):
            self.clients.add(self)
            logging.info('connected {}'.format(self.address))
              
        def handleClose(self):
            self.clients.remove(self)
            logging.info('closed {}'.format(self.address))

    def __init__(self, host, port, linkHost, linkPort):
        super().__init__(host, port, TagoEventServer.EventHandler)
        self.host = host
        self.port = port
        self.run_thread = True  
        self.events = None

        threading.Thread(target=self.event_worker, args=(linkHost, linkPort)).start()

    def serve(self):
        logging.info('Running websocket server on {}:{}'.format(self.host, self.port))
        threading.Thread(target=self.serveforever).start()    

    def stop(self):
        logging.warning('exit server')
        self.run_thread = False
        if self.events:
            self.events.stop()
        logging.warning('exit server DONE')

    def event_worker(self, host, port):
        self.events = TagoEvents(host, port)
        while self.run_thread:
            time.sleep(0.05)
            try:
                result = self.events.getNext()
                for c in TagoEventServer.clients.copy():
                    c.sendMessage(json.dumps(result))
            except Exception as e:
                        logging.error('event_worker Exception: {}'.format(e))
                        time.sleep(1)
                        continue

tagoapi = None
##
## REST API
##
app = Flask(__name__)
cors = CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.route("/api/<tid>/rename_device", methods=['POST', 'GET'])
def rename(tid):
    tagoapi.rename_device(tid, request.json['name'])
    return {'status': 'ok'}
    
@app.route("/api/<tid>/rename_channel", methods=['POST', 'GET'])
def rename_channel(tid):
    tagoapi.rename_channel(tid, request.json['ch'], request.json['name'])
    return {'status': 'ok'}

@app.route("/api/<tid>/info")
def info(tid):
    return tagoapi.device_info(tid)

@app.route("/api/<tid>/identify")
def identify(tid):
    tagoapi.identify_device(tid)
    return {'status': 'ok'}

@app.route("/api/<tid>/reboot")
def reboot(tid):
    tagoapi.reboot_device(tid)
    return {'status': 'ok'}

@app.route("/api/<tid>/do", methods=['POST', 'GET'])
def take_action(tid):
    commands = request.json
    for item in commands:
        # logging.info(item)
        channel = item.get('ch', 0)
        if channel == 0: continue

        action = item.get('action', 'nop').upper()
        value = item.get('value', 0)
        rate = item.get('rate', 100)

        tagoapi.device_action(tid, channel, action, value, rate)
                             
    return {'status': 'ok'}

## rescan all devices on the bus
@app.route("/api/rescan_all")
def rescan_all():
    return tagoapi.rescan_bus()

## list all devices
@app.route("/api/list_devices")
def list():
    return tagoapi.list_devices()

@app.route("/<path:path>")
def static_files_root(path):
    return send_from_directory('build', path)

@app.errorhandler(404)
def page_not_found(e):
    return send_from_directory('build', 'index.html')

@app.route("/static/css/<path:path>")
def static_files_static_css(path):
    return send_from_directory('build/static/css', path)

@app.route("/static/js/<path:path>")
def static_files_static_js(path):
    return send_from_directory('build/static/js', path)


import os

def run_server(bridge_url, http_port=5000, ws_port=8000, db_path='data'):
    global tagoapi
    ## Extract port from host url if provided
    parts = bridge_url.split(':')
    if len(parts) > 1:
        bridge_port = int(parts[1])
    else:
        bridge_port = 27
    bridge_host = parts[0]

    HTTP_PORT = int(os.environ.get('HTTP_PORT', http_port))
    WS_PORT = int(os.environ.get('WS_PORT', ws_port))
    MB_HOST = os.environ.get('MB_HOST', bridge_host)
    MB_PORT = int(os.environ.get('MB_PORT', bridge_port))
    DB_PATH = os.environ.get('DB_PATH', 'data')

    server = TagoEventServer('', WS_PORT, MB_HOST, MB_PORT)
    server.serve()

    tagoapi = TagoApi(host=MB_HOST, port=MB_PORT, dbpath=DB_PATH)    

    ## start API server
    app.run(host='0.0.0.0', port=HTTP_PORT, threaded=False, debug=False)
