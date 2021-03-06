from datetime import datetime, timedelta
import socket
import random
import string
from subprocess import check_output, PIPE

from flask import Flask, make_response, request, render_template, \
    send_file, redirect, flash
from flask_sockets import Sockets
from math import ceil
import gevent.queue

import mmo
from json_dumper import dump_as_json
from export import excel
from mmo.binoculars import ButtonType
from mmo.database import Database
from mmo.export.gpx import export_gpx


class Registry:
    def __init__(self):
        self.binoculars = None


registry = Registry()

app = Flask(__name__, static_url_path='/static', template_folder='templates')
app.secret_key = ''.join(
    random.SystemRandom().choice(string.ascii_uppercase + string.digits)
    for _ in range(20))
app.config['hostname'] = socket.gethostname()

# Websocket
sockets = Sockets(app)
clients = []
event_queue = gevent.queue.Queue()


@sockets.route('/echo')
def echo_socket(ws):
    while not ws.closed:
        msg = ws.receive()
        if msg is None:
            break
        ws.send(msg)


class ObservationBackend(object):
    """
    A backend
    """

    def __init__(self):
        self.clients = list()

    def __iter_data(self):
        while True:
            obs = event_queue.get()
            app.logger.info("New observation. Yielding observation")
            yield obs

    def register(self, client):
        self.clients.append(client)

    def send(self, client, data):
        try:
            # First check if 'comment' update
            if data.get('type', '') == 'comment':
                app.logger.debug("Updating comment {}".format(data.get('id')))
                client.send(dump_as_json(data))
            else:
                for k, v in data.items():
                    if data[k] is None:
                        data[k] = '-'
                    elif k in ('gm0', 'gm1', 'gm2'):
                        continue
                    elif type(v) is float:
                        data[k] = round(v, 2)
                    elif type(v) is datetime:
                        time_zone = 0
                        h, m = divmod(time_zone * 60, 60)
                        data[k] = (v - timedelta(hours=h, minutes=m)).strftime("%Y-%m-%d %H:%M:%S")
                fields = data.keys()
                data['fields'] = fields
                client.send(dump_as_json(data))
        except Exception:
            app.logger.debug("ObservationBackend exception occured. Remove client: {}".format(client))
            self.clients.remove(client)

    def run(self):
        app.logger.info("Running ObservationBackend")
        for obs in self.__iter_data():
            for client in self.clients:
                gevent.spawn(self.send, client, obs)

    def start(self):
        app.logger.info("Start ObservationBackend")
        gevent.spawn(self.run)

# Start our backend to broadcast new observations to all listening web clients
obsBackend = ObservationBackend()
obsBackend.start()


@sockets.route('/observations')
def observations(ws):
    obsBackend.register(ws)
    while not ws.closed:
        # Context switch while ObservationBackend.start runs in the background
        gevent.sleep(0.1)


def long_click_handler(obs):
    event_queue.put(obs)


def short_click_handler(obs):
    event_queue.put(obs)


@app.route('/data.csv')
def dump_csv():
    text = registry.binoculars.storage.dump_csv()
    response = make_response(text, 200)
    response.headers['Content-type'] = "text/csv"
    return response


@app.route('/data.html')
def dump_table():
    fields = request.args.get('fields')
    page = request.args.get('page')

    if page is None:
        page = 1
    else:
        page = int(page)
    num_records = mmo.config.get_num_records()
    records_per_page = mmo.config.observations_to_show_on_main_page

    pages = range(1, int(ceil(num_records / records_per_page) + 2))
    rows = registry.binoculars.storage.dump_list(limit=records_per_page, page=page)

    if request.args.get('reverse') is not None:
        rows.reverse()

    if not fields:
        if len(rows) == 0:
            fields = []
        else:
            fields = rows[0].keys()
    else:
        fields = fields.split(',')

    def format_column(data):
        if data is None:
            return '-'
        if type(data) is float:
            return round(data, 2)
        if type(data) is datetime:
            time_zone = 0
            if request.args.get('tz'):
                time_zone = float(request.args.get('tz'))
            h, m = divmod(time_zone * 60, 60)
            return (data - timedelta(hours=h, minutes=m)).strftime("%Y-%m-%d %H:%M:%S")
        return data

    return render_template('dataTable.html',
                           rows=rows,
                           format_column=format_column,
                           fields=fields,
                           page=page,
                           pages=pages)


@app.route('/data.xlsx')
def dump_excel():
    filename = excel.export(registry.binoculars.storage.dump_list())
    response = send_file(filename, as_attachment=True, attachment_filename="mmo_export.xlsx")
    return response


@app.route('/config.html', methods=['GET'])
def get_config():
    config = Database.get_config()
    return render_template('config.html', axisOptions=['A', 'B'], **config)


@app.route('/config.html', methods=['POST'])
def set_config():
    Database.set_config(request.form)
    flash("Config was updated")
    mmo.config.refresh()
    registry.binoculars.config_updated()
    return redirect('/config.html')


@app.route('/data.json')
def dump_json():
    data_list = registry.binoculars.storage.dump_list()

    text = dump_as_json(data_list)
    print text
    response = make_response(text, 200)
    response.headers['Content-type'] = "application/json"
    return response


@app.route('/track.gpx')
def gpx_track():
    gpx = export_gpx(Database.get_positions())
    response = make_response(gpx, 200)
    response.headers['Content-type'] = "application/gpx+xml"
    return response


@app.route('/')
def index():
    return render_template('index.html', status=mmo.status)


@app.route('/comments', methods=['POST'])
def save_comment():
    observation_id = request.form['id']
    comment = request.form['comment']
    Database.store_comment(observation_id, comment)
    event_queue.put({"type": "comment",
                     "id": "comment_" + str(observation_id),
                     "comment": comment})
    return unicode("Stored comment for id {}: {}").format(observation_id, comment)


@app.route('/set_time', methods=['POST', 'GET'])
def set_time_from_gps():
    if request.method == 'GET':
        if not mmo.status.gps_connected:
            return "GPS must be connected"
        if mmo.status.last_gps_fix is None:
            return "GPS has not received any time signal yet"
        return render_template('time_config.html',
                               system_time=mmo.status.get_system_time(),
                               gps_time=mmo.status.last_gps_fix.timestamp,
                               hardware_clock_time=check_output(["sudo", "hwclock", "-r"]))
    elif request.method == 'POST':
        date_updated_ok = mmo.status.update_system_time_from_gps()
        if date_updated_ok:
            flash("Time was updated")
        else:
            flash("Could not set time", "error")
        return redirect('/set_time')


@app.route('/delete_observations', methods=['GET'])
def delete_observations():
    if request.method == 'GET':
        Database.delete_observations()
        return redirect('/data.html')


@app.route('/click/<length>', methods=['POST'])
def click(length):
    if length == 'short':
        registry.binoculars.button_click(ButtonType.short)
    elif length == 'long':
        registry.binoculars.button_click(ButtonType.long)
    else:
        return "", 404
    return "OK " + length


def prestart(binoculars):
    registry.binoculars = binoculars
    mmo.config.refresh()
    registry.binoculars.config_updated()


def start(binoculars, **kwargs):
    try:
        app.run(host="0.0.0.0", **kwargs)

    except Exception:
        print("Got exception in web_server:start")
        print("Stopping fake spatial service..")
        binoculars.spatial.stop()
        print("Done!")
