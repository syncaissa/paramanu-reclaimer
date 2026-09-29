# Minimal job server for a RunPod pod: PUT /upload (tar.gz), POST /run, GET files.
# Every request must carry the header X-Token matching $JOB_TOKEN.
import http.server, os, subprocess, tarfile, io
TOKEN = os.environ["JOB_TOKEN"]
WORK = "/work"
os.makedirs(WORK, exist_ok=True)
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=WORK, **k)
    def ok(self):
        if self.headers.get("X-Token") != TOKEN:
            self.send_response(403); self.end_headers(); return False
        return True
    def do_GET(self):
        if self.ok():
            super().do_GET()
    def do_PUT(self):
        if not self.ok(): return
        data = self.rfile.read(int(self.headers["Content-Length"]))
        tarfile.open(fileobj=io.BytesIO(data), mode="r:gz").extractall(WORK)
        self.send_response(200); self.end_headers(); self.wfile.write(b"uploaded\n")
    def do_POST(self):
        if not self.ok(): return
        cmd = self.rfile.read(int(self.headers["Content-Length"])).decode()
        subprocess.Popen(["bash", "-c", cmd], cwd=WORK,
                         stdout=open(f"{WORK}/job.log", "ab"), stderr=subprocess.STDOUT)
        self.send_response(200); self.end_headers(); self.wfile.write(b"started\n")
http.server.ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()
