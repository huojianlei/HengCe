"""Independent worker probes; each audit policy dies with its child process."""
import sys,os,json,subprocess,unittest,ssl,threading,http.server,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'desktop'),str(ROOT/'fenxi')]
import ai_worker as worker

def child(mode):
    from unittest.mock import patch
    if mode=='sandbox':
        worker.install_sandbox('example.invalid',443,{'127.0.0.1'})
        attempts=[lambda:open(str(ROOT/'desktop/distribution.json')),lambda:os.listdir(ROOT),lambda:subprocess.run(['cmd','/c','echo forbidden']),lambda:worker.socket.create_connection(('192.0.2.1',443)),lambda:eval('1+1')]
        for attempt in attempts:
            try:attempt()
            except PermissionError:continue
            raise AssertionError('sandbox permitted forbidden operation')
        print('PASS');return
    if mode=='disabled':
        assert worker.run({'op':'chat','dataAccess':False,'data':{'raw':'SECRET'},'apiKey':'SECRET'})['status']=='权限关闭'
        print('PASS');return
    if mode=='tls':
        data={'schemaVersion':'ai-results/1','period':'2027-06','variance':[]}
        answer=worker.run({'op':'chat','dataAccess':True,'data':data,'apiKey':'test-only','endpoint':os.environ['AI_TEST_ENDPOINT'],'question':'解释'})
        assert answer['status']=='通过',answer
        print('PASS');return
    captured={}
    class Response:
        status=200
        def read(self,*args):return json.dumps({'choices':[{'message':{'content':'本次差异需要人工复核。'}}]}).encode()
    class Connection:
        def __init__(self,*args,**kwargs):pass
        def request(self,method,path,body,headers):
            captured.update(json.loads(body));assert 'SECRET' not in body.decode()
            try:open(str(ROOT/'desktop/distribution.json'))
            except PermissionError:pass
            else:raise AssertionError('model request ran outside file sandbox')
        def getresponse(self):return Response()
        def close(self):pass
    worker.http.client.HTTPSConnection=Connection
    worker.socket.getaddrinfo=lambda *a,**kw:[(2,1,6,'',('127.0.0.1',443))]
    data={'schemaVersion':'ai-results/1','period':'2027-06','variance':[{'subject':'收入','period':'2027-06','actualAmount':1234,'raw':'SECRET'}],'raw':'SECRET'}
    answer=worker.run({'op':'chat','dataAccess':True,'data':data,'apiKey':'test','endpoint':'https://example.invalid','question':'解释'})
    assert answer['status']=='通过',answer
    assert captured['messages'] and captured['stream'] is False
    print('PASS')

class WorkerTests(unittest.TestCase):
    def test_execution_sandbox(self):self.probe('sandbox')
    def test_disabled_does_not_open_files_or_network(self):self.probe('disabled')
    def test_outbound_payload_and_verified_reply(self):self.probe('payload')
    def test_real_https_transport_still_works_inside_sandbox(self):
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes,serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        directory=ROOT/'desktop/qa/ai-sandbox';directory.mkdir(parents=True,exist_ok=True)
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')]);now=datetime.datetime.now(datetime.timezone.utc)
        cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1)).not_valid_after(now+datetime.timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]),False).sign(key,hashes.SHA256())
        cp=directory/'test-cert.pem';kp=directory/'test-key.pem'
        cp.write_bytes(cert.public_bytes(serialization.Encoding.PEM));kp.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                raw=json.dumps({'choices':[{'message':{'content':'请人工复核差异。'}}]}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def log_message(self,*args):pass
        server=http.server.HTTPServer(('127.0.0.1',0),Handler)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cp,kp);server.socket=context.wrap_socket(server.socket,server_side=True)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            env={**os.environ,'SSL_CERT_FILE':str(cp),'AI_TEST_ENDPOINT':f'https://localhost:{server.server_port}'}
            r=subprocess.run([sys.executable,'-B','-X','utf8',__file__,'tls'],capture_output=True,text=True,cwd=ROOT,env=env,timeout=30)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        finally:server.shutdown();server.server_close();thread.join()
    def probe(self,mode):
        r=subprocess.run([sys.executable,'-B','-X','utf8',__file__,mode],capture_output=True,text=True,cwd=ROOT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},timeout=30)
        self.assertEqual(r.returncode,0,r.stderr+r.stdout);self.assertIn('PASS',r.stdout)
if __name__=='__main__':
    if len(sys.argv)>1:child(sys.argv[1])
    else:unittest.main()
