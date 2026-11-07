"""Run on Linux/Pi; all service and data writes stay in an isolated fixture."""
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

SCRIPTS = Path(sys.argv.pop(1)).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]/'deploy'


class RollbackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='eeye-rollback-fixture-',dir='/var/tmp')
        self.root=Path(self.temporary.name)
        for name in ('data','snapshots','bin','releases/old/app','releases/new/app','releases/old/.venv/bin','releases/new/.venv/bin'):
            (self.root/name).mkdir(parents=True,exist_ok=True)
        for name in ('old','new'):
            (self.root/'releases'/name/'app/app.py').write_text('# test fixture\n')
            gunicorn=self.root/'releases'/name/'.venv/bin/gunicorn'
            gunicorn.write_text('#!/bin/sh\nexit 0\n'); gunicorn.chmod(0o700)
        self.old=self.root/'releases/old'; self.new=self.root/'releases/new'
        (self.root/'current').symlink_to(self.old)
        (self.root/'data/record.txt').write_text('original record')
        (self.root/'device.env').write_text('ORIGINAL=1\n')
        (self.root/'eeye.service').write_text('original unit\n')
        fake=self.root/'bin/systemctl'
        fake.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "'+str(self.root/'service.log')+'"\nexit 0\n')
        fake.chmod(0o700)
        fixture=self.root
        class Health(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                failed=(fixture/'current/fail-health').exists()
                if failed: (fixture/'data/new-record.txt').write_text('preserve after rollback')
                self.send_response(503 if failed else 200)
                self.send_header('Content-Type','application/json'); self.end_headers()
                self.wfile.write(json.dumps(dict(ready=True,protocol_version=1,
                    mock_mode=(fixture/'current/mock-mode').exists())).encode())
            def log_message(self,*args): pass
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Health)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.env=dict(os.environ,EEYE_TEST_ROOT=str(self.root),EEYE_HEALTH_TIMEOUT='1',
            EEYE_HEALTH_URL=f'http://127.0.0.1:{self.server.server_port}/api/storage/status')

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.temporary.cleanup()

    def run_script(self,name,*args):
        return subprocess.run(['bash',str(SCRIPTS/name),*map(str,args)],env=self.env,
                              capture_output=True,text=True,timeout=15)

    def test_successful_activation_snapshots_and_explicit_rollback_keeps_new_records(self):
        result=self.run_script('activate.sh',self.new)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual((self.root/'current').resolve(),self.new)
        self.assertEqual(Path((self.root/'previous-release').read_text().strip()),self.old)
        snapshots=list((self.root/'snapshots').iterdir())
        self.assertEqual(len(snapshots),1)
        self.assertEqual((snapshots[0]/'data/record.txt').read_text(),'original record')
        (self.root/'data/new-record.txt').write_text('keep this')
        result=self.run_script('rollback.sh')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual((self.root/'current').resolve(),self.old)
        self.assertEqual((self.root/'data/new-record.txt').read_text(),'keep this')

    def test_failed_health_restores_previous_code_without_losing_new_data(self):
        (self.new/'fail-health').touch()
        result=self.run_script('activate.sh',self.new)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual((self.root/'current').resolve(),self.old)
        self.assertTrue((self.root/'data/new-record.txt').is_file(),result.stdout+result.stderr)
        self.assertIn('rollback', (result.stdout+result.stderr).lower())

    def test_mock_mode_cannot_pass_deployment_health_gate(self):
        (self.new/'mock-mode').touch()
        result=self.run_script('activate.sh',self.new)
        self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual((self.root/'current').resolve(),self.old)

    def test_snapshot_failure_restarts_the_original_service(self):
        fake=self.root/'bin/cp'; fake.write_text('#!/bin/sh\nexit 1\n'); fake.chmod(0o700)
        self.env['PATH']=str(self.root/'bin')+os.pathsep+self.env['PATH']
        result=self.run_script('activate.sh',self.new)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual((self.root/'current').resolve(),self.old)
        self.assertIn('start eeye.service',(self.root/'service.log').read_text())


if __name__=='__main__': unittest.main()
