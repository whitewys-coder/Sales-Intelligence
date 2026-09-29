import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

class HTTPTests(unittest.TestCase):
    def test_authenticated_demo_flow(self):
        with tempfile.TemporaryDirectory() as data:
            with socket.socket() as s:
                s.bind(('127.0.0.1', 0))
                port = s.getsockname()[1]
            env = dict(os.environ, APP_MODE='demo', APP_TOKEN='test-token-not-for-deployment',
                       DATA_DIR=data, PORT=str(port), HOST='127.0.0.1', SCHEDULE_ENABLED='false')
            process = subprocess.Popen([sys.executable, '-m', 'sales_agent'], env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            base = f'http://127.0.0.1:{port}'
            def call(path, payload=None, auth=True):
                headers = {'Content-Type': 'application/json'}
                if auth: headers['Authorization'] = 'Bearer ' + env['APP_TOKEN']
                req = urllib.request.Request(base+path, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
                with urllib.request.urlopen(req, timeout=5) as r: return r.status, json.load(r)
            try:
                for _ in range(50):
                    try:
                        call('/health',auth=False)
                        break
                    except urllib.error.URLError: time.sleep(.05)
                with self.assertRaises(urllib.error.HTTPError) as error: call('/api/state',auth=False)
                self.assertEqual(error.exception.code,401)
                self.assertEqual(call('/api/run',{})[0],202)
                for _ in range(50):
                    state=call('/api/state')[1]
                    if state['runs'] and state['runs'][0]['status']=='completed': break
                    time.sleep(.05)
                self.assertEqual(state['runs'][0]['status'],'completed')
                d=state['drafts'][0]
                result=call('/api/drafts/approve',{'id':d['id'],'hash':d['hash'],'evidence_reviewed':True})
                self.assertEqual(result[1]['status'],'approved')
                with self.assertRaises(urllib.error.HTTPError) as error: call('/api/drafts/send',{'id':d['id']})
                self.assertEqual(error.exception.code,400)
                self.assertEqual(len(call('/api/export')[1]['accounts']),1)
                with urllib.request.urlopen(base+'/') as r:
                    self.assertIn('Agate',r.read().decode())
                    self.assertIn("frame-ancestors 'none'",r.headers['Content-Security-Policy'])
            finally:
                process.terminate()
                process.wait(timeout=5)
                process.stderr.close()
