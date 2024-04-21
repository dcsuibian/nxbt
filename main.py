# if '__main__' == __name__:
#     # reconnect_address = None
#     reconnect_address = '98:B6:E9:E6:88:7F'
#     server = ControllerServer(controller_type=ControllerTypes.PRO_CONTROLLER, reconnect_address=reconnect_address)
#     controller_process = Thread(target=server.run)
#     controller_process.start()
#     while True:
#         print(server.state)
#         if 'connected' == server.state['state']:
#             break
#         time.sleep(1)
#     print('连接成功')
#     packet = json.loads(json.dumps(DIRECT_INPUT_IDLE_PACKET))
#     while True:
#         packet['B'] = True
#         server.state['direct_input'] = packet
#         time.sleep(0.5)
#         packet['B'] = False
#         print(server.state)
#         time.sleep(0.001)
import json
import logging
import threading
import time

from flask import Flask, request, jsonify

from nxbt import ControllerServer
from nxbt.controller import ControllerTypes
from nxbt.controller.input import DIRECT_INPUT_IDLE_PACKET

app = Flask(__name__)

wrapper = dict()
wrapper['packet'] = json.loads(json.dumps(DIRECT_INPUT_IDLE_PACKET))
wrapper['recording'] = False
wrapper['playing'] = False

app.logger.disabled = True

log = logging.getLogger('werkzeug')
log.disabled = True


@app.route('/api/gamepad', methods=['POST'])
def get_gamepad():
    wrapper['packet'] = request.json
    return jsonify({'message': 'Received your POST request!'})


@app.route('/api/get_recording', methods=['GET'])
def get_recording():
    return jsonify(wrapper['recording'])


@app.route('/api/set_recording', methods=['POST'])
def set_recording():
    wrapper['recording'] = request.json
    return 'ok'


@app.route('/api/get_playing', methods=['GET'])
def get_playing():
    return jsonify(wrapper['playing'])


@app.route('/api/set_playing', methods=['POST'])
def set_playing():
    wrapper['playing'] = request.json
    return 'ok'


@app.route('/api/get_input_list', methods=['GET'])
def get_input_list():
    return jsonify(wrapper['input_list'])


@app.route('/api/set_input_list', methods=['POST'])
def set_input_list():
    wrapper['input_list'] = request.json
    return 'ok'


@app.route('/api/clear_input_list', methods=['GET'])
def clear_input_list():
    wrapper['input_list'] = []
    return 'ok'


def main_thread():
    reconnect_address = '98:B6:E9:E6:88:7F'
    server = ControllerServer(controller_type=ControllerTypes.PRO_CONTROLLER, reconnect_address=reconnect_address)
    controller_process = threading.Thread(target=server.run)
    controller_process.start()
    while True:
        print(server.state)
        if 'connected' == server.state['state']:
            break
        time.sleep(1)
    print('连接成功')
    wrapper['input_list'] = []
    while True:
        if wrapper['playing']:
            for action in wrapper['input_list']:
                server.state['direct_input'] = action
                time.sleep(1.0 / 1000)
            print('又一轮循环完成')
            time.sleep(5)
            continue
        server.state['direct_input'] = json.loads(json.dumps(wrapper['packet']))
        if wrapper['recording']:
            wrapper['input_list'].append(json.loads(json.dumps(wrapper['packet'])))
        time.sleep(1.0 / 1000)


if __name__ == '__main__':
    thread = threading.Thread(target=main_thread)
    thread.start()
    # 运行 Flask 应用
    app.run(host='0.0.0.0', debug=False)
    print('Flash running')
