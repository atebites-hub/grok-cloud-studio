#!/usr/bin/env python3
from __future__ import annotations
import hashlib, hmac, json, os, subprocess, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
ROOT = Path(os.environ.get('GCS_ROOT', Path(__file__).resolve().parents[2]))
SEND = Path(os.environ.get('GCS_A2A_SEND', str(ROOT / 'scripts' / 'a2a' / 'send.sh')))
SECRET = os.environ.get('GCS_WEBHOOK_SECRET', '')
INSECURE = os.environ.get('GCS_WEBHOOK_INSECURE', '0') == '1'
HOST = os.environ.get('GCS_WEBHOOK_HOST', '127.0.0.1')
PORT = int(os.environ.get('GCS_WEBHOOK_PORT', '8788'))
DEFAULT_SEAT = os.environ.get('GCS_DEFAULT_SEAT', 'ops')

def verify(sig_header: str, body: bytes) -> bool:
    if INSECURE and not SECRET:
        return True
    if not SECRET or not sig_header.startswith('sha256='):
        return False
    expected = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_header.split('=', 1)[1].strip())

def a2a_ping(seat: str, text: str) -> None:
    subprocess.run(['bash', str(SEND), seat, text], check=False)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write('webhook: ' + (fmt % args) + '\n')
    def do_GET(self):
        if urlparse(self.path).path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"ok":true,"service":"gcs-webhook"}')
            return
        self.send_response(404)
        self.end_headers()
    def do_POST(self):
        if urlparse(self.path).path not in ('/hook', '/webhook', '/'):
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length)
        sig = self.headers.get('X-GCS-Signature') or self.headers.get('X-Hub-Signature-256') or ''
        if not verify(sig, body):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"ok":false}')
            return
        try:
            payload = json.loads(body.decode() or '{}')
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return
        status = (payload.get('status') or (payload.get('run') or {}).get('status') or '').upper()
        if status == 'CANCELED':
            status = 'CANCELLED'
        agent_id = payload.get('id') or payload.get('agentId') or (payload.get('agent') or {}).get('id') or 'unknown'
        seat = payload.get('seat') or DEFAULT_SEAT
        pr = payload.get('prUrl') or payload.get('pr') or 'none'
        if status in ('FINISHED', 'ERROR', 'CANCELLED', 'EXPIRED'):
            kind = 'PR_READY' if status == 'FINISHED' and pr not in (None, '', 'none') else ('INSPECT' if status == 'CANCELLED' else 'FLEET_DONE')
            a2a_ping(str(seat), f'{kind} bc-id={agent_id} status={status} pr={pr}')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

def main() -> int:
    if not SECRET and not INSECURE:
        print('GCS_WEBHOOK_SECRET required (or GCS_WEBHOOK_INSECURE=1)', file=sys.stderr)
        return 2
    print(f'gcs-webhook listening on http://{HOST}:{PORT}')
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
