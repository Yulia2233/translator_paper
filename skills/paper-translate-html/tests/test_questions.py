"""Exercise durable submission, replay, scope validation, and answer readback."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError


class Questions(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'paper').mkdir()
            (root/'paper/paper.json').write_text(json.dumps({'source_sha256':'a'*64,'pages':14}))
            server = Path(__file__).resolve().parents[1]/'scripts/question_server.py'
            process = subprocess.Popen([sys.executable,str(server),'--out',tmp],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
            try:
                base = process.stdout.readline().strip().removesuffix('/index.html')
                def get():
                    with urlopen(base+'/api/questions?paper=paper') as response:
                        return json.load(response)
                token = get()['token']
                q = dict(id='test',paper_id='paper',source_sha256='a'*64,page=8,section='原文第 8 页',quote='<img src=x onerror=alert(1)>',question='解释指标？',created_at='2026-10-23T00:00:00Z')
                def post(data, headers=None):
                    req=Request(base+'/api/questions',json.dumps(data).encode(),headers=headers or {'X-Reader-Token':token,'Content-Type':'application/json'})
                    with urlopen(req) as response:
                        return json.load(response)
                self.assertTrue(post(q)['saved'])
                post(q)
                self.assertEqual(len(get()['questions']),1)
                for bad in [[], None, dict(q,page=99),dict(q,paper_id='../paper'),dict(q,source_sha256='b'*64),dict(q,question='changed')]:
                    with self.assertRaises(HTTPError) as error:post(bad)
                    error.exception.close()
                with self.assertRaises(HTTPError) as error:post(q,{'X-Reader-Token':'bad'})
                error.exception.close()
                with self.assertRaises(HTTPError) as error:post(q,{'X-Reader-Token':token,'Origin':'https://example.com'})
                error.exception.close()
                data=json.loads((root/'问题标注.json').read_text())
                data['questions'][0].update(status='answered',answer='回答及 PDF 第 8 页依据')
                (root/'问题标注.json').write_text(json.dumps(data))
                post(q)
                self.assertEqual(get()['questions'][0]['answer'],'回答及 PDF 第 8 页依据')
                (root/'问题标注.json').write_text('{"schema_version":1,"questions":[null]}')
                with self.assertRaises(HTTPError) as error:get()
                self.assertEqual(error.exception.code,500)
                error.exception.close()
                with self.assertRaises(HTTPError) as error:post(q)
                error.exception.close()
                self.assertEqual(json.loads((root/'问题标注.json').read_text())['questions'],[None])
            finally:
                process.terminate();process.wait(timeout=5);process.stdout.close()


if __name__ == '__main__':unittest.main()
