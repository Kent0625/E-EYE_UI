"""Exercise the deployed API using an explicitly synthetic, temporary session."""
import io
import requests
from PIL import Image

base = 'http://192.168.137.106:5000'
client = requests.Session()
client.headers['Origin'] = base
status = client.get(base+'/api/status', timeout=25).json()
assert status['mock_mode'] is False, status
session = client.post(base+'/api/sessions', json=dict(participant_code='TEST-DEPLOY-SYNTHETIC',
    site='Synthetic integration verification', consent_age=True, consent_signed=True), timeout=20)
session.raise_for_status()
session_id = session.json()['id']
path = base+'/api/sessions/'+session_id
try:
    # An absent distance sensor must prevent an actual recording.
    if status['tof'] != 'ok':
        blocked = client.post(path+'/record',json={'eye':'OD'},timeout=20)
        assert blocked.status_code in (400,409), blocked.text
    image = io.BytesIO()
    Image.new('RGB',(100,100),'white').save(image,'PNG')
    receipt = client.post(path+'/receipts',data={'participant_code':'TEST-DEPLOY-SYNTHETIC'},
        files={'image':('synthetic-test.png',image.getvalue(),'image/png')},timeout=20)
    receipt.raise_for_status()
    receipt_id = receipt.json()['id']
    body = dict(confirmed=True,participant_code='TEST-DEPLOY-SYNTHETIC',receipt_id=receipt_id,
        reference_method='three_readings',eyes={'OD':{'readings':[
            {'sphere_D':-1,'cylinder_D':-.5}, {'sphere_D':-1.25,'cylinder_D':-.5},
            {'sphere_D':-1.5,'cylinder_D':-.5}]}})
    saved = client.post(path+'/confirmed-ground-truth',json=body,timeout=20)
    saved.raise_for_status()
    truth = saved.json()['eyes']['OD']['ground_truth']
    assert truth['sphere_D']==-1.25 and truth['se_D']==-1.5, truth
    assert truth['receipt_id']==receipt_id and len(truth['readings'])==3
    assert client.get(path+'/receipts/'+receipt_id+'/image',timeout=20).content==image.getvalue()
    exported = client.get(base+'/api/export.csv',timeout=20)
    assert exported.ok and 'TEST-DEPLOY-SYNTHETIC' in exported.text and 'three_readings' in exported.text
    assert client.get(path,timeout=20).json()['eyes']['OD']['ground_truth']['confirmed'] is True
    print('PASS: real-mode server, sensor capture gate, receipt upload/original retrieval, confirmed three-reading mean, persistence and CSV linkage')
finally:
    deleted = client.delete(path,timeout=20)
    deleted.raise_for_status()
    assert client.get(path,timeout=20).status_code==404
    print('PASS: synthetic session and receipt cleanup')
