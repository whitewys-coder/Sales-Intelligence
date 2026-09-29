import fcntl
import hmac
import json
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo
from .engine import Engine, DEFAULT_SCOPE, digest


def schedule_tick(engine, local):
    key = local.date().isoformat()
    if local.hour < engine.c.schedule_hour:
        return
    if any(r.get('schedule_key') == key for r in engine.db.all('runs')):
        return
    scope = engine.db.get('settings', 'scope') or {'value': DEFAULT_SCOPE}
    engine.run(scope['value'], schedule_key=key)


def serve(config):
    Path(config.data_dir).mkdir(parents=True, exist_ok=True)
    lockfile = open(Path(config.data_dir) / 'process.lock', 'a')
    try:
        fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError('Another server is using this DATA_DIR') from None
    engine = Engine(config)
    # Crash recovery is explicit: do not rerun a job or an ambiguous SMTP operation.
    for r in engine.db.all('runs'):
        if r['status'] == 'running':
            r['status'] = 'interrupted'
            engine.db.put('runs', r)
    for d in engine.db.all('drafts'):
        if d['status'] == 'sending':
            d['status'] = 'unknown'
            engine.db.put('drafts', d)
    zone = ZoneInfo(config.timezone)
    stop = threading.Event()

    def scheduler():
        while not stop.wait(20):
            if config.schedule_enabled:
                try:
                    schedule_tick(engine, datetime.now(zone))
                except Exception as exc:
                    engine.db.event('Scheduler', 'failed', type(exc).__name__)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # No credentials, message bodies, or query strings in console logs.

        def respond(self, code, value, content_type='application/json'):
            body = value.encode() if isinstance(value, str) else json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', content_type + '; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            actual = self.headers.get('Authorization', '')
            return hmac.compare_digest(actual, 'Bearer ' + config.token)

        def do_GET(self):
            if self.path == '/health':
                return self.respond(200, {'status': 'ok'})
            assets = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
            if self.path in assets:
                name, mime = assets[self.path]
                return self.respond(200, (Path(__file__).parent.parent / 'static' / name).read_text(), mime)
            if not self.authorized():
                return self.respond(401, {'error': 'Unauthorized'})
            if self.path in ('/api/state', '/api/export'):
                data = engine.state()
                for d in data['drafts']:
                    d['hash'] = digest(d)
                return self.respond(200, data)
            self.respond(404, {'error': 'Not found'})

        def do_POST(self):
            if not self.authorized():
                return self.respond(401, {'error': 'Unauthorized'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 64000:
                    raise ValueError('Invalid request size')
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError('JSON object required')
                if self.path == '/api/run':
                    if engine.lock.locked():
                        return self.respond(409, {'error': 'Workflow busy'})
                    scope = engine.db.get('settings', 'scope') or {'value': DEFAULT_SCOPE}
                    threading.Thread(target=engine.run, args=(scope['value'],), daemon=True).start()
                    return self.respond(202, {'status': 'started'})
                if self.path == '/api/scope':
                    value = str(data['scope']).strip()
                    if not 10 <= len(value) <= 4000:
                        raise ValueError('Scope must contain 10–4000 characters')
                    engine.db.put('settings', {'id': 'scope', 'value': value})
                    return self.respond(200, {'status': 'saved'})
                if self.path == '/api/drafts/edit':
                    value = engine.edit(data['id'], str(data['subject']), str(data['body']))
                elif self.path == '/api/drafts/approve':
                    value = engine.approve(data['id'], data['hash'], data.get('evidence_reviewed') is True)
                elif self.path == '/api/drafts/send':
                    value = engine.send(data['id'])
                elif self.path == '/api/feedback':
                    if not isinstance(data.get('valid'), bool):
                        raise ValueError('valid must be boolean')
                    value = engine.feedback(data['id'], data['valid'], str(data.get('reason', '')))
                else:
                    return self.respond(404, {'error': 'Not found'})
                self.respond(200, value)
            except (ValueError, KeyError, TypeError) as exc:
                self.respond(400, {'error': str(exc)[:300]})
            except Exception as exc:
                engine.db.event('API', 'failed', type(exc).__name__)
                self.respond(502, {'error': 'Operation failed. Check run history and connection configuration.'})

    threading.Thread(target=scheduler, daemon=True).start()
    httpd = ThreadingHTTPServer((config.bind, config.port), Handler)
    print(f'Sales Agent {config.mode}: http://{config.bind}:{config.port}', flush=True)
    try:
        httpd.serve_forever()
    finally:
        stop.set()
        httpd.server_close()
        lockfile.close()
