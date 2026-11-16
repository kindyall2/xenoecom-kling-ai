"""
Kling AI Video Generator Backend
Hệ thống kết nối trực tiếp với Klinggiare API
Không yêu cầu cài thêm thư viện (chạy 100% bằng Python tiêu chuẩn)
"""

import http.server
import socketserver
import json
import urllib.request
import urllib.error
import uuid
import os
import mimetypes

PORT = int(os.environ.get("PORT", 8080))
API_BASE = "https://klinggiare.com"
API_KEY = os.environ.get("KLING_API_KEY", "kling_sk_6bV7-Nvtk9GruKUDL-uMl0OfUXQEldZt_3lQF0MyLhE")

class KlingHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        pub = os.path.join(os.path.dirname(__file__), "public")
        serve_dir = pub if os.path.exists(pub) and os.path.exists(os.path.join(pub, "index.html")) else os.path.dirname(__file__)
        super().__init__(*args, directory=serve_dir, **kwargs)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def send_json(self, status_code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        
        # API: Lấy thông tin số dư ví
        if path == "/api/wallet":
            try:
                req = urllib.request.Request(
                    f"{API_BASE}/api/v1/ext/wallet",
                    headers={
                        "Authorization": f"Bearer {API_KEY}",
                        "User-Agent": "Mozilla/5.0"
                    }
                )
                with urllib.request.urlopen(req, timeout=10) as res:
                    data = json.loads(res.read().decode("utf-8"))
                    self.send_json(200, {"success": True, "wallet": data})
            except urllib.error.HTTPError as e:
                err_content = e.read().decode("utf-8")
                self.send_json(e.code, {"success": False, "error": err_content})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        # API: Lấy bảng giá & mô hình
        if path == "/api/prices":
            try:
                req = urllib.request.Request(
                    f"{API_BASE}/api/v1/prices",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=10) as res:
                    data = json.loads(res.read().decode("utf-8"))
                    self.send_json(200, {"success": True, "prices": data})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        # API: Kiểm tra trạng thái Job (/api/job/501)
        if path.startswith("/api/job/"):
            job_id = path.replace("/api/job/", "").strip()
            try:
                req = urllib.request.Request(
                    f"{API_BASE}/api/v1/ext/jobs/{job_id}",
                    headers={
                        "Authorization": f"Bearer {API_KEY}",
                        "User-Agent": "Mozilla/5.0"
                    }
                )
                with urllib.request.urlopen(req, timeout=10) as res:
                    job_data = json.loads(res.read().decode("utf-8"))
                    
                    # Nếu job thành công, tự động lấy luôn video download URL
                    video_url = None
                    if job_data.get("status") == "success":
                        try:
                            v_req = urllib.request.Request(
                                f"{API_BASE}/api/v1/ext/jobs/{job_id}/video-url",
                                headers={
                                    "Authorization": f"Bearer {API_KEY}",
                                    "User-Agent": "Mozilla/5.0"
                                }
                            )
                            with urllib.request.urlopen(v_req, timeout=10) as v_res:
                                v_data = json.loads(v_res.read().decode("utf-8"))
                                video_url = v_data.get("url")
                        except Exception:
                            video_url = job_data.get("providerVideoUrl") or job_data.get("providerCdnUrl")

                    self.send_json(200, {
                        "success": True, 
                        "job": job_data,
                        "videoUrl": video_url
                    })
            except urllib.error.HTTPError as e:
                self.send_json(e.code, {"success": False, "error": e.read().decode("utf-8")})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        # Mặc định: Phục vụ file tĩnh (HTML, CSS, JS) trong thư mục public
        super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]
        content_length = int(self.headers.get("Content-Length", 0))

        # API: Báo giá ước tính (Quote)
        if path == "/api/quote":
            body = self.rfile.read(content_length)
            try:
                req_data = json.loads(body.decode("utf-8"))
                req = urllib.request.Request(
                    f"{API_BASE}/api/v1/ext/batches/quote",
                    data=json.dumps(req_data).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {API_KEY}",
                        "Content-Type": "application/json",
                        "User-Agent": "Mozilla/5.0"
                    }
                )
                with urllib.request.urlopen(req, timeout=10) as res:
                    quote_data = json.loads(res.read().decode("utf-8"))
                    self.send_json(200, {"success": True, "quote": quote_data})
            except urllib.error.HTTPError as e:
                self.send_json(e.code, {"success": False, "error": e.read().decode("utf-8")})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        # API: Tạo video (Tạo Batch)
        if path == "/api/create-video":
            body = self.rfile.read(content_length)
            try:
                req_data = json.loads(body.decode("utf-8"))
                
                # Payload gửi sang Klinggiare
                batch_payload = {
                    "prompt": req_data.get("prompt"),
                    "settings": {
                        "model": req_data.get("model", "4.0-flash"),
                        "durationSeconds": int(req_data.get("durationSeconds", 5)),
                        "aspectRatio": req_data.get("aspectRatio", "16:9"),
                        "resolution": req_data.get("resolution", "720p"),
                        "audio": bool(req_data.get("audio", True))
                    }
                }
                
                # Nếu có ảnh đầu vào (Image to Video)
                if req_data.get("imageKeys"):
                    batch_payload["imageKeys"] = req_data.get("imageKeys")

                idempotency_key = str(uuid.uuid4())

                req = urllib.request.Request(
                    f"{API_BASE}/api/v1/ext/batches",
                    data=json.dumps(batch_payload).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {API_KEY}",
                        "Content-Type": "application/json",
                        "Idempotency-Key": idempotency_key,
                        "User-Agent": "Mozilla/5.0"
                    }
                )
                with urllib.request.urlopen(req, timeout=15) as res:
                    batch_data = json.loads(res.read().decode("utf-8"))
                    jobs = batch_data.get("jobs", [])
                    job_id = jobs[0].get("id") if jobs else None
                    self.send_json(200, {
                        "success": True, 
                        "batch": batch_data,
                        "jobId": job_id
                    })
            except urllib.error.HTTPError as e:
                self.send_json(e.code, {"success": False, "error": e.read().decode("utf-8")})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        # API: Tải ảnh lên (Upload ảnh trực tiếp)
        if path == "/api/upload-image":
            # Chuyển tiếp trực tiếp multipart data sang klinggiare
            content_type = self.headers.get("Content-Type")
            body = self.rfile.read(content_length)
            try:
                req = urllib.request.Request(
                    f"{API_BASE}/api/v1/ext/uploads",
                    data=body,
                    headers={
                        "Authorization": f"Bearer {API_KEY}",
                        "Content-Type": content_type,
                        "User-Agent": "Mozilla/5.0"
                    }
                )
                with urllib.request.urlopen(req, timeout=30) as res:
                    upload_res = json.loads(res.read().decode("utf-8"))
                    self.send_json(200, {"success": True, "data": upload_res})
            except urllib.error.HTTPError as e:
                self.send_json(e.code, {"success": False, "error": e.read().decode("utf-8")})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        self.send_json(404, {"error": "Not Found"})

def run():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), KlingHandler) as httpd:
        print(f"=====================================================")
        print(f"🚀 XENOECOM KLING AI WEB SERVER DANG CHAY TAI:")
        print(f"👉 http://localhost:{PORT}")
        print(f"👉 http://127.0.0.1:{PORT}")
        print(f"=====================================================")
        print(f"Nhan Ctrl+C de dung server.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nDa dung server.")

if __name__ == "__main__":
    run()
