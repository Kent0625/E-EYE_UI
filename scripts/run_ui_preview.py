"""Open the operator interface with no sample records or connected hardware."""
import argparse
import os
from pathlib import Path
import sys

project = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--host', default='127.0.0.1')
parser.add_argument('--port', type=int, default=5080)
args = parser.parse_args()
data = project/'output'/'ui-preview'
data.mkdir(parents=True, exist_ok=True)
os.environ.update(EEYE_MOCK='0', EEYE_DEVICE_DISCONNECTED='1',
                  EEYE_DB=str(data/'operator.sqlite3'), EEYE_DATA=str(data/'data'),
                  EEYE_RECEIPTS=str(data/'receipts'))
sys.path.insert(0, str(project))
from app.app import create_app
from app import store
from flask import abort, send_file
app = create_app()
store.set_setting('research_mode', '1')

@app.get('/demo/operator.apk')
def preview_apk():
    apk = project/'output'/'eeye-operator-debug.apk'
    if not apk.is_file(): abort(404)
    return send_file(apk, as_attachment=True, download_name='eeye-operator-responsive-test.apk')

print(f'Operator interface: http://{args.host}:{args.port} — connect the Pi to record.', flush=True)
app.run(host=args.host, port=args.port, threaded=True, use_reloader=False)
