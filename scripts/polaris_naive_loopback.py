#!/usr/bin/env python3
"""Real isolated TLS/H2 Naive exchange with positive and wrong-CA controls."""
from pathlib import Path
import argparse,hashlib,http.server,json,os,socket,subprocess,threading,time

def port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def request(proxy,target):
    with socket.create_connection(('127.0.0.1',proxy),timeout=3) as s:
        s.settimeout(12);s.sendall(f'GET http://127.0.0.1:{target}/polaris-naive-h2 HTTP/1.1\r\nHost: 127.0.0.1:{target}\r\nConnection: close\r\n\r\n'.encode());out=b''
        while True:
            b=s.recv(65536)
            if not b:break
            out+=b
        return out

def main(core,output,runner=None,guest=None):
    output.mkdir(parents=True,exist_ok=False);token=b'polaris-actual-static-cronet-naive-tls-h2';counts=[]
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            counts.append(self.path);self.send_response(200);self.send_header('Content-Length',str(len(token)));self.end_headers();self.wfile.write(token)
        def log_message(self,*a):pass
    target=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=target.serve_forever,daemon=True).start();tp=target.server_port;np=port();processes=[];logs=[]
    def cert(name):
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(output/(name+'.key')),'-out',str(output/(name+'.crt')),'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost','-addext','basicConstraints=critical,CA:TRUE'],capture_output=True,check=True)
    def start(name,config,listen):
        if guest and name.startswith('client-'):
            config['inbounds'][0].update(listen='0.0.0.0',listen_port=1080)
            config['outbounds'][0]['server']='10.0.2.2'
            phase=name.removeprefix('client-')
            ca=subprocess.check_output([*guest['ssh'],'cat /etc/ssl/certs/ca-certificates.crt'])
            cert=ca+b'\n'+(output/(phase+'.crt')).read_bytes()
            subprocess.run([*guest['ssh'],'cat > /tmp/polaris-fixture-ca.pem'],input=cert,check=True)
            config['outbounds'][0]['tls']['certificate_path']='/tmp/polaris-fixture-ca.pem'
            subprocess.run([*guest['ssh'],'cat > /tmp/polaris-fixture-client.json'],input=json.dumps(config).encode(),check=True)
            subprocess.run([*guest['ssh'],"set -eu; if /etc/init.d/sing-box running; then /etc/init.d/sing-box stop; fi; uci set sing-box.main.enabled=1; uci set sing-box.main.conffile=/tmp/polaris-fixture-client.json; uci commit sing-box; /etc/init.d/sing-box start"],check=True)
            for _ in range(200):
                ready=subprocess.run([*guest['ssh'],"netstat -lnt | grep -q ':1080 '"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
                if ready.returncode==0:return
                time.sleep(.1)
            raise TimeoutError(name+' guest procd')
        p=output/(name+'.json');p.write_text(json.dumps(config));f=(output/(name+'.log')).open('wb');logs.append(f);proc=subprocess.Popen([*list(runner or []),str(core),'run','-c',str(p)],stdout=f,stderr=subprocess.STDOUT,env={k:v for k,v in os.environ.items() if k not in ['LD_PRELOAD','LD_LIBRARY_PATH']});processes.append(proc)
        for _ in range(200):
            if proc.poll() is not None:raise RuntimeError(f'{name} exited {proc.returncode}: '+(output/(name+'.log')).read_text())
            try:
                with socket.create_connection(('127.0.0.1',listen),timeout=.1):return
            except OSError:time.sleep(.05)
        raise TimeoutError(name)
    try:
        cert('trusted');cert('wrong')
        start('naive-server',{'log':{'level':'trace'},'inbounds':[{'type':'naive','tag':'verified-h2-in','listen':'127.0.0.1','listen_port':np,'network':'tcp','users':[{'username':'polaris-test','password':'temporary-loopback-only'}],'tls':{'enabled':True,'certificate_path':str(output/'trusted.crt'),'key_path':str(output/'trusted.key'),'alpn':['h2']}}],'outbounds':[{'type':'direct'}]},np)
        results={}
        for name in ['wrong','trusted']:
            cp=guest['proxyPort'] if guest else port();start('client-'+name,{'log':{'level':'trace'},'inbounds':[{'type':'mixed','listen':'127.0.0.1','listen_port':cp}], 'outbounds':[{'type':'naive','tag':'measured-static-cronet','server':'127.0.0.1','server_port':np,'username':'polaris-test','password':'temporary-loopback-only','quic':False,'tls':{'enabled':True,'server_name':'localhost','certificate_path':str(output/(name+'.crt'))}}]},cp)
            try:response=request(cp,tp)
            except (OSError,TimeoutError) as e:response=str(e).encode()
            (output/(name+'-response.bin')).write_bytes(response);results[name]={'accepted':b'200 OK' in response and token in response,'bytes':len(response),'sha256':hashlib.sha256(response).hexdigest()}
            if name=='wrong':assert results[name]['accepted'] is False and not counts,'untrusted TLS reached target'
            else:assert results[name]['accepted'] is True and counts==['/polaris-naive-h2'],'actual TLS-H2 Naive request failed'
        receipt={'schema':'polaris-naive-loopback-validation-v1','core':{'bytes':core.stat().st_size,'sha256':hashlib.sha256(core.read_bytes()).hexdigest()},'transport':'TCP TLS; server ALPN only h2; client QUIC=false; fixed static Cronet Naive','certificateVerification':'wrong CA rejected; matching CA accepted; insecure never enabled','responses':results,'targetPaths':counts,'realDeviceAcceptance':False,'externalNetwork':False,'runner':list(runner or []),'actualOpenWrtGuestClient':bool(guest),'caBundleUsed':bool(guest),'certificates':{name:{'bytes':(output/(name+'.crt')).stat().st_size,'sha256':hashlib.sha256((output/(name+'.crt')).read_bytes()).hexdigest()} for name in ['wrong','trusted']}};(output/'RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
    finally:
        if guest:subprocess.run([*guest['ssh'],'/etc/init.d/sing-box stop'],check=False)
        for p in reversed(processes):
            if p.poll() is None:p.terminate()
        for p in processes:
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for f in logs:f.close()
        target.shutdown();target.server_close()
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--core',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--runner',nargs='*',default=[]);o=a.parse_args();main(o.core.resolve(),o.output.resolve(),o.runner)
