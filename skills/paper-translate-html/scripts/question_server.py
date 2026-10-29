"""Loopback-only reader and durable question queue. No model/API calls."""
import argparse
import json
import os
from pathlib import Path
import secrets
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import urlsplit, parse_qs, unquote


def serve(root, port):
    root = Path(root).resolve()
    queue = root / '问题标注.json'
    token = secrets.token_urlsafe(32)
    lock = Lock()

    def read():
        if not queue.exists():
            return {'schema_version': 1, 'questions': []}
        data = json.loads(queue.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('schema_version') != 1 or not isinstance(data.get('questions'), list):
            raise ValueError('问题文件格式无效；未覆盖文件')
        if any(not isinstance(q, dict) or not isinstance(q.get('id'), str) or not isinstance(q.get('paper_id'), str) for q in data['questions']):
            raise ValueError('问题记录格式无效；未覆盖文件')
        return data

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def valid(self):
            origin = 'http://' + self.headers.get('Host', '')
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}' and self.headers.get('Origin', origin) == origin

        def send_json(self, value, code=200):
            data = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self.valid():
                return self.send_json({'error': 'Invalid host or origin'}, 403)
            url = urlsplit(self.path)
            if url.path == '/api/questions':
                paper = parse_qs(url.query).get('paper', [''])[0]
                try:
                    with lock:
                        data = read()
                    return self.send_json({'token': token, 'questions': [q for q in data['questions'] if q['paper_id'] == paper]})
                except (ValueError, KeyError):
                    return self.send_json({'error': '问题文件损坏，请让 agent 检查；未覆盖文件'}, 500)
            path = (root / unquote(url.path).lstrip('/')).resolve()
            if not path.is_relative_to(root) or any(x.startswith('.') for x in path.relative_to(root).parts):
                return self.send_error(403)
            return super().do_GET()

        def do_POST(self):
            if not self.valid() or self.path != '/api/questions' or self.headers.get('X-Reader-Token') != token:
                return self.send_json({'error': 'Invalid submission'}, 403)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 100000:
                    raise ValueError('提交大小无效')
                q = json.loads(self.rfile.read(length))
                if not isinstance(q, dict):
                    raise ValueError('提交内容必须为对象')
                for key, limit in [('id',100),('paper_id',200),('source_sha256',64),('quote',20000),('question',4000),('created_at',100),('section',200)]:
                    if not isinstance(q.get(key), str) or not q[key].strip() or len(q[key]) > limit:
                        raise ValueError('无效字段：' + key)
                paper = (root / q['paper_id']).resolve()
                if paper.parent != root:
                    raise ValueError('无效论文路径')
                info = json.loads((paper / 'paper.json').read_text())
                if q['source_sha256'] != info['source_sha256']:
                    raise ValueError('论文版本不一致，请刷新阅读页')
                page = q.get('page')
                if page is not None and (type(page) is not int or not 1 <= page <= info['pages']):
                    raise ValueError('无效页码')
                clean = {k:q[k] for k in ['id','paper_id','source_sha256','quote','question','created_at','section']}
                clean.update(page=page, status='pending', answer=None)
                with lock:
                    data = read()
                    existing = next((x for x in data['questions'] if x['id'] == clean['id']), None)
                    if existing and any(existing.get(k) != clean[k] for k in ['paper_id','quote','question','source_sha256']):
                        raise ValueError('问题 ID 冲突')
                    if not existing:
                        data['questions'].append(clean)
                        temp = queue.with_suffix('.tmp')
                        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                        os.replace(temp, queue)
                return self.send_json({'saved': True, 'id': clean['id']})
            except (ValueError, KeyError, OSError) as exc:
                return self.send_json({'error': str(exc)}, 400)

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    url = f'http://127.0.0.1:{server.server_port}/index.html'
    (root / '.question-server.json').write_text(json.dumps({'url':url,'pid':os.getpid()}))
    print(url, flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    serve(args.out, args.port)
