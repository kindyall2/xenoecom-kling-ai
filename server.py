"""
Kling AI Video Generator Backend - Xenoecom Studio
Hệ thống kết nối Klinggiare API + Supabase Cloud Database (Vĩnh Viễn) + Quản trị Admin
Không yêu cầu cài thêm thư viện (chạy 100% bằng Python tiêu chuẩn)
"""

import http.server
import socketserver
import json
import urllib.request
import urllib.error
import uuid
import os
import hashlib
import time
import re
import urllib.parse
import mimetypes
import db

PORT = int(os.environ.get("PORT", 8080))
API_BASE = "https://klinggiare.com"
API_KEY = os.environ.get("KLING_API_KEY", "kling_sk_6bV7-Nvtk9GruKUDL-uMl0OfUXQEldZt_3lQF0MyLhE")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Theanh2025@")

# Cấu hình Grok Video (CinAI Minimax H3-RH Enhanced 15s 1080p - 750đ / video - 15 credits/key dùng xong bỏ)
CINAI_ORIGIN = "https://cinai.app"
CINAI_API_BASE = f"{CINAI_ORIGIN}/api/v1"
GROK_MODEL_SLUG = "minimax-h3-rh-enhanced"
GROK_VIDEO_PRICE = 750
GROK_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Xenoecom-Grok-Studio/1.0"

def cinai_json_request(method, path, api_key, payload=None, timeout=45):
    url = f"{CINAI_API_BASE}{path}"
    headers = {"User-Agent": GROK_USER_AGENT, "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw)
            except Exception:
                data = {"raw": raw}
            return resp.status, data
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except Exception:
            data = {"error": raw or str(e)}
        return e.code, data
    except Exception as e:
        return 502, {"error": f"Không kết nối được tới máy chủ Grok AI: {e}"}

def extract_cinai_video_urls(obj):
    urls = []
    def walk(node):
        if isinstance(node, str):
            s = node.strip()
            if s.startswith(("/api/", "/media/", "/uploads/")):
                s = f"{CINAI_ORIGIN}{s}"
            if s.startswith(("http://", "https://")) and s not in urls:
                urls.append(s)
        elif isinstance(node, dict):
            priority = ("resultUrls", "result_urls", "video_url", "video", "videos", "output", "outputs", "urls", "url", "files", "media", "result")
            for k in priority:
                if k in node:
                    walk(node[k])
            for k, v in node.items():
                if k not in priority:
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)
    walk(obj)
    return urls

def upload_image_to_public_host(filename, content_type, file_bytes):
    safe_name = re.sub(r'["\r\n]', "_", filename or "image.jpg")
    ct = content_type or mimetypes.guess_type(safe_name)[0] or "image/jpeg"
    # 1. Litterbox (72h direct URL)
    try:
        boundary = f"----XenoGrokBoundary{uuid.uuid4().hex}"
        body = b"".join([
            f'--{boundary}\r\nContent-Disposition: form-data; name="reqtype"\r\n\r\nfileupload\r\n'.encode("utf-8"),
            f'--{boundary}\r\nContent-Disposition: form-data; name="time"\r\n\r\n72h\r\n'.encode("utf-8"),
            f'--{boundary}\r\nContent-Disposition: form-data; name="fileToUpload"; filename="{safe_name}"\r\nContent-Type: {ct}\r\n\r\n'.encode("utf-8"),
            file_bytes,
            f"\r\n--{boundary}--\r\n".encode("utf-8"),
        ])
        req = urllib.request.Request(
            "https://litterbox.catbox.moe/resources/internals/api.php",
            data=body,
            headers={"User-Agent": GROK_USER_AGENT, "Content-Type": f"multipart/form-data; boundary={boundary}", "Content-Length": str(len(body))},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            url = resp.read().decode("utf-8", errors="replace").strip()
            if resp.status == 200 and url.startswith(("http://", "https://")):
                return True, url
    except Exception:
        pass
    # 2. Uguu.se fallback
    try:
        boundary = f"----XenoGrokBoundary{uuid.uuid4().hex}"
        body = b"".join([
            f'--{boundary}\r\nContent-Disposition: form-data; name="files[]"; filename="{safe_name}"\r\nContent-Type: {ct}\r\n\r\n'.encode("utf-8"),
            file_bytes,
            f"\r\n--{boundary}--\r\n".encode("utf-8"),
        ])
        req = urllib.request.Request(
            "https://uguu.se/upload",
            data=body,
            headers={"User-Agent": GROK_USER_AGENT, "Content-Type": f"multipart/form-data; boundary={boundary}", "Content-Length": str(len(body))},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            files = data.get("files") or []
            if files and files[0].get("url"):
                return True, files[0]["url"]
    except Exception:
        pass
    # 3. Tmpfiles fallback
    try:
        boundary = f"----XenoGrokBoundary{uuid.uuid4().hex}"
        body = b"".join([
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{safe_name}"\r\nContent-Type: {ct}\r\n\r\n'.encode("utf-8"),
            file_bytes,
            f"\r\n--{boundary}--\r\n".encode("utf-8"),
        ])
        req = urllib.request.Request(
            "https://tmpfiles.org/api/v1/upload",
            data=body,
            headers={"User-Agent": GROK_USER_AGENT, "Content-Type": f"multipart/form-data; boundary={boundary}", "Content-Length": str(len(body))},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            raw_url = (data.get("data") or {}).get("url") or ""
            if raw_url:
                return True, raw_url.replace("http://", "https://").replace("tmpfiles.org/", "tmpfiles.org/dl/", 1)
    except Exception as e:
        return False, str(e)
    return False, "Không thể tải ảnh lên máy chủ trung gian"

# Token tĩnh cho Admin - đảm bảo không bị logout khi khởi động lại server
ADMIN_STATIC_TOKEN = "xenoecom_adm_" + hashlib.sha256(("xenoecom_admin_salt_" + ADMIN_PASSWORD).encode("utf-8")).hexdigest()[:24]
ADMIN_TOKENS = set([ADMIN_STATIC_TOKEN])

def hash_password(password):
    return hashlib.sha256(("xenoecom_salt_" + password).encode("utf-8")).hexdigest()

def get_customer_price(model, duration_seconds, is_motion):
    if is_motion:
        return 600
    if model == "4.0":
        return 400
    if model == "3.0":
        return 500
    return 300 if int(duration_seconds) == 5 else 500

class KlingHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        pub = os.path.join(os.path.dirname(__file__), "public")
        serve_dir = pub if os.path.exists(pub) and os.path.exists(os.path.join(pub, "index.html")) else os.path.dirname(__file__)
        super().__init__(*args, directory=serve_dir, **kwargs)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Token")
        self.end_headers()

    def send_json(self, status_code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def get_authenticated_user(self):
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header.split(" ")[1].strip()
        return db.get_user_by_session_token(token)

    def is_admin_authenticated(self):
        token = self.headers.get("X-Admin-Token", "").strip()
        return bool(token and (token == ADMIN_STATIC_TOKEN or token in ADMIN_TOKENS))

    def do_GET(self):
        path = self.path.split("?")[0]

        # ROUTE: Trang Admin Panel (/admin)
        if path in ["/admin", "/admin/"]:
            admin_file = os.path.join(os.path.dirname(__file__), "public", "admin.html")
            if not os.path.exists(admin_file):
                admin_file = os.path.join(os.path.dirname(__file__), "admin.html")
            if os.path.exists(admin_file):
                with open(admin_file, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

        # API ADMIN: Thống kê tổng quan (/api/admin/stats)
        if path == "/api/admin/stats":
            if not self.is_admin_authenticated():
                self.send_json(401, {"success": False, "error": "Yêu cầu quyền Quản trị viên!"})
                return
            try:
                total_users, total_user_balance, total_videos = db.get_admin_stats()

                # Lấy số dư ví Klinggiare gốc
                kling_balance = 0
                try:
                    req = urllib.request.Request(
                        f"{API_BASE}/api/v1/ext/wallet",
                        headers={"Authorization": f"Bearer {API_KEY}", "User-Agent": "Mozilla/5.0"}
                    )
                    with urllib.request.urlopen(req, timeout=5) as res:
                        w_data = json.loads(res.read().decode("utf-8"))
                        kling_balance = w_data.get("balance", 0)
                except Exception as e:
                    print("Error fetching Kling wallet:", e)

                self.send_json(200, {
                    "success": True,
                    "totalUsers": total_users,
                    "totalUserBalance": total_user_balance,
                    "totalVideos": total_videos,
                    "klingWalletBalance": kling_balance
                })
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        # API ADMIN: Danh sách tất cả khách hàng (/api/admin/users)
        if path == "/api/admin/users":
            if not self.is_admin_authenticated():
                self.send_json(401, {"success": False, "error": "Yêu cầu quyền Quản trị viên!"})
                return
            try:
                user_list = db.get_admin_users()
                self.send_json(200, {"success": True, "users": user_list})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        # API ADMIN: Danh sách tất cả video (/api/admin/videos)
        if path == "/api/admin/videos":
            if not self.is_admin_authenticated():
                self.send_json(401, {"success": False, "error": "Yêu cầu quyền Quản trị viên!"})
                return
            try:
                vid_list = db.get_admin_videos(40)
                self.send_json(200, {"success": True, "videos": vid_list})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return
        
        # API: Lấy thông tin tài khoản hiện tại
        if path == "/api/auth/me":
            user = self.get_authenticated_user()
            if not user:
                self.send_json(401, {"success": False, "error": "Chưa đăng nhập"})
            else:
                self.send_json(200, {"success": True, "user": user})
            return

        # API ADMIN: Lấy danh sách & thống kê Kho Key Grok (/api/admin/grok-keys)
        if path == "/api/admin/grok-keys":
            if not self.is_admin_authenticated():
                self.send_json(401, {"success": False, "error": "Yêu cầu quyền Quản trị viên!"})
                return
            summary = db.get_grok_keys_summary()
            self.send_json(200, {"success": True, **summary})
            return

        # API GROK: Kiểm tra trạng thái job Grok Video (/api/grok/job/<call_id>)
        if path.startswith("/api/grok/job/"):
            call_id = path.replace("/api/grok/job/", "").strip()
            rec = db.get_grok_video_by_call_id(call_id)
            if not rec:
                self.send_json(404, {"success": False, "error": "Không tìm thấy lệnh Grok Video"})
                return
            if rec.get("status") == "success" and rec.get("video_url"):
                self.send_json(200, {"success": True, "status": "success", "videoUrl": rec["video_url"]})
                return
            if rec.get("status") == "failed":
                self.send_json(200, {"success": True, "status": "failed", "error": "Tạo video thất bại (Đã hoàn tiền)"})
                return

            used_key = rec.get("used_key") or ""
            st_code, cdata = cinai_json_request("GET", f"/calls/{urllib.parse.quote(call_id)}", used_key, timeout=15)
            call_obj = None
            if isinstance(cdata, dict):
                call_obj = (cdata.get("data") or {}).get("call") if isinstance(cdata.get("data"), dict) else cdata.get("call")
            if isinstance(call_obj, dict):
                cst = (call_obj.get("status") or "processing").lower()
                if cst == "succeeded":
                    urls = extract_cinai_video_urls(call_obj.get("output"))
                    vurl = urls[0] if urls else None
                    if vurl:
                        db.update_grok_video_url(call_id, vurl)
                        self.send_json(200, {"success": True, "status": "success", "videoUrl": vurl})
                        return
                elif cst in ("failed", "canceled", "cancelled", "error"):
                    if rec.get("status") == "processing":
                        db.update_grok_video_failed(call_id)
                        if rec.get("user_id") and rec.get("cost"):
                            db.adjust_user_balance(rec["user_id"], int(rec["cost"]))
                    self.send_json(200, {"success": True, "status": "failed", "error": str(call_obj.get("error") or "Lỗi xử lý")})
                    return
                self.send_json(200, {"success": True, "status": cst})
                return
            self.send_json(200, {"success": True, "status": "processing"})
            return

        # API: Lấy lịch sử video của khách (Tự động đồng bộ trạng thái các video đang render từ Klinggiare & Grok)
        if path == "/api/user/videos":
            user = self.get_authenticated_user()
            if not user:
                self.send_json(401, {"success": False, "error": "Chưa đăng nhập"})
                return
            videos = db.get_user_videos(user["id"], limit=30)
            # Kiểm tra và cập nhật tối đa 5 video đang ở trạng thái processing gần nhất
            checked = 0
            for v in videos:
                if v.get("status") == "processing" and checked < 5:
                    if v.get("provider") == "grok" and v.get("externalId"):
                        checked += 1
                        cid = v["externalId"]
                        ukey = v.get("usedKey") or ""
                        try:
                            _, cdata = cinai_json_request("GET", f"/calls/{urllib.parse.quote(cid)}", ukey, timeout=8)
                            call_obj = (cdata.get("data") or {}).get("call") if isinstance(cdata, dict) and isinstance(cdata.get("data"), dict) else (cdata.get("call") if isinstance(cdata, dict) else None)
                            if isinstance(call_obj, dict):
                                cst = (call_obj.get("status") or "").lower()
                                if cst == "succeeded":
                                    urls = extract_cinai_video_urls(call_obj.get("output"))
                                    if urls:
                                        db.update_grok_video_url(cid, urls[0])
                                        v["videoUrl"] = urls[0]
                                        v["status"] = "success"
                                elif cst in ("failed", "canceled", "cancelled", "error"):
                                    db.update_grok_video_failed(cid)
                                    v["status"] = "failed"
                                    if v.get("cost"):
                                        db.adjust_user_balance(user["id"], int(v["cost"]))
                        except Exception:
                            pass
                    elif v.get("jobId"):
                        checked += 1
                        jid = v["jobId"]
                        try:
                            jreq = urllib.request.Request(
                                f"{API_BASE}/api/v1/ext/jobs/{jid}",
                                headers={"Authorization": f"Bearer {API_KEY}", "User-Agent": "Mozilla/5.0"}
                            )
                            with urllib.request.urlopen(jreq, timeout=6) as jres:
                                jdata = json.loads(jres.read().decode("utf-8"))
                            jst = jdata.get("status")
                            if jst == "success":
                                vurl = None
                                try:
                                    vreq = urllib.request.Request(
                                        f"{API_BASE}/api/v1/ext/jobs/{jid}/video-url",
                                        headers={"Authorization": f"Bearer {API_KEY}", "User-Agent": "Mozilla/5.0"}
                                    )
                                    with urllib.request.urlopen(vreq, timeout=6) as vres:
                                        vurl = json.loads(vres.read().decode("utf-8")).get("url")
                                except Exception:
                                    vurl = jdata.get("providerVideoUrl") or jdata.get("providerCdnUrl")
                                if vurl:
                                    db.update_video_url(jid, vurl)
                                    v["videoUrl"] = vurl
                                    v["status"] = "success"
                            elif jst in ("failed", "canceled"):
                                db.update_video_failed(jid)
                                v["status"] = "failed"
                                if v.get("cost"):
                                    db.adjust_user_balance(user["id"], int(v["cost"]))
                        except Exception:
                            pass
                # Ẩn API key nội bộ trước khi trả về trình duyệt khách hàng
                v.pop("usedKey", None)
            self.send_json(200, {"success": True, "videos": videos})
            return

        # API: Kiểm tra trạng thái bảo trì hệ thống
        if path == "/api/system/status":
            try:
                req = urllib.request.Request(
                    f"{API_BASE}/api/v1/system/status",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=8) as res:
                    data = json.loads(res.read().decode("utf-8"))
                    self.send_json(200, {"success": True, "status": data})
            except urllib.error.HTTPError as e:
                if e.code == 503:
                    self.send_json(200, {
                        "success": True,
                        "status": {
                            "maintenance": True,
                            "maintenanceMessage": "Hệ thống đang bảo trì để nâng cấp (dự kiến hoàn tất trong khoảng 10 phút). Video đang render vẫn tiếp tục bình thường."
                        }
                    })
                    return
                self.send_json(e.code, {"success": False, "error": str(e)})
            except Exception as e:
                self.send_json(200, {
                    "success": True,
                    "status": {
                        "maintenance": True,
                        "maintenanceMessage": "Máy chủ AI đang bảo trì định kỳ. Quý khách vui lòng quay lại sau ít phút!"
                    }
                })
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

                        # Cập nhật link video vào database nếu có
                        if video_url:
                            db.update_video_url(job_id, video_url)

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

        # API: Tải video MP4 trực tiếp về máy (Đảm bảo điện thoại iPhone/Android tải file MP4 thật, không ra file web)
        if path == "/api/download-video":
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query)
            target_url = query.get("url", [None])[0]
            if not target_url:
                self.send_json(400, {"error": "Thiếu link video để tải!"})
                return
            try:
                req = urllib.request.Request(target_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=60) as res:
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Disposition", 'attachment; filename="kling_video.mp4"')
                    cl = res.headers.get("Content-Length")
                    if cl:
                        self.send_header("Content-Length", cl)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    while True:
                        chunk = res.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            except Exception as e:
                self.send_json(500, {"error": str(e)})
            return

        super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]
        content_length = int(self.headers.get("Content-Length", 0))

        # API ADMIN: Đăng nhập Admin (/api/admin/login)
        if path == "/api/admin/login":
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body.decode("utf-8"))
                pwd = data.get("password", "")
                if pwd == ADMIN_PASSWORD:
                    token = ADMIN_STATIC_TOKEN
                    ADMIN_TOKENS.add(token)
                    self.send_json(200, {"success": True, "adminToken": token})
                else:
                    self.send_json(400, {"success": False, "error": "Mật khẩu Quản trị Admin không chính xác!"})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        # API ADMIN: Thêm hàng loạt API Key Grok vào kho (/api/admin/grok-keys/add)
        if path == "/api/admin/grok-keys/add":
            if not self.is_admin_authenticated():
                self.send_json(401, {"success": False, "error": "Yêu cầu quyền Quản trị viên!"})
                return
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body.decode("utf-8"))
                keys_text = data.get("keysText", "") or ""
                raw_keys = [x.strip() for x in re.split(r"[\r\n,;\s]+", keys_text) if x.strip()]
                added = db.add_grok_keys(raw_keys)
                summary = db.get_grok_keys_summary()
                self.send_json(200, {"success": True, "added": added, **summary})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        # API ADMIN: Xóa API Key Grok hoặc dọn các key đã dùng (/api/admin/grok-keys/delete)
        if path == "/api/admin/grok-keys/delete":
            if not self.is_admin_authenticated():
                self.send_json(401, {"success": False, "error": "Yêu cầu quyền Quản trị viên!"})
                return
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body.decode("utf-8"))
                if data.get("action") == "clear_used":
                    db.clear_used_grok_keys()
                elif data.get("id"):
                    db.delete_grok_key(int(data["id"]))
                summary = db.get_grok_keys_summary()
                self.send_json(200, {"success": True, **summary})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        # API GROK: Tải ảnh lên host trung gian cho Grok Video (/api/grok/upload-image)
        if path == "/api/grok/upload-image":
            content_type = self.headers.get("Content-Type", "")
            body = self.rfile.read(content_length)
            try:
                m = re.search(r"boundary=([^;\s]+)", content_type)
                if not m:
                    raise ValueError("Missing multipart boundary")
                boundary = m.group(1).strip('"').encode("utf-8")
                parts = body.split(b"--" + boundary)
                uploaded_url = None
                for part in parts:
                    if b"Content-Disposition" not in part:
                        continue
                    part = part.lstrip(b"\r\n")
                    if b"\r\n\r\n" not in part:
                        continue
                    header_bytes, file_bytes = part.split(b"\r\n\r\n", 1)
                    if file_bytes.endswith(b"\r\n"):
                        file_bytes = file_bytes[:-2]
                    header_str = header_bytes.decode("utf-8", errors="ignore")
                    fn_match = re.search(r'filename="([^"]+)"', header_str)
                    filename = fn_match.group(1) if fn_match else "image.jpg"
                    ct_match = re.search(r"Content-Type:\s*([^\r\n]+)", header_str, re.IGNORECASE)
                    part_ct = ct_match.group(1).strip() if ct_match else "image/jpeg"
                    ok, res_url = upload_image_to_public_host(filename, part_ct, file_bytes)
                    if ok:
                        uploaded_url = res_url
                        break
                    else:
                        raise ValueError(res_url)
                if not uploaded_url:
                    raise ValueError("Không nhận được dữ liệu ảnh")
                self.send_json(200, {"success": True, "url": uploaded_url})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        # API GROK: Tạo video Grok 15s · 1080p · 750đ (Dùng 1 key 15 credits rồi bỏ luôn key đó)
        if path == "/api/grok/create-video":
            user = self.get_authenticated_user()
            if not user:
                self.send_json(401, {"success": False, "error": "AUTH_REQUIRED", "message": "Vui lòng đăng nhập hoặc tạo tài khoản trước khi tạo video!"})
                return
            body = self.rfile.read(content_length)
            try:
                req_data = json.loads(body.decode("utf-8"))
                prompt = (req_data.get("prompt") or "").strip()
                image_url = (req_data.get("imageUrl") or "").strip()
                aspect_ratio = req_data.get("aspectRatio") or "9:16"
                if aspect_ratio not in ("16:9", "9:16", "1:1"):
                    aspect_ratio = "9:16"
                grok_duration = 10 if int(req_data.get("duration", 15)) == 10 else 15

                if not image_url:
                    self.send_json(400, {"success": False, "error": "Vui lòng tải lên 1 ảnh đầu vào cho Grok Video!"})
                    return
                if not prompt:
                    prompt = "Chuyển động tự nhiên, mượt mà, chất lượng điện ảnh 1080p sắc nét"

                cost = 500 if grok_duration == 10 else GROK_VIDEO_PRICE
                if user["balance"] < cost:
                    self.send_json(402, {
                        "success": False,
                        "error": "INSUFFICIENT_BALANCE",
                        "message": f"Số dư của bạn không đủ ({user['balance']} đ). Lượt Grok Video {grok_duration}s 1080p cần {cost} đ. Vui lòng nạp thêm tiền!"
                    })
                    return

                candidates = db.get_active_grok_keys()
                if not candidates:
                    self.send_json(503, {
                        "success": False,
                        "error": "Kho máy chủ Grok Video tạm thời hết lượt khả dụng. Vui lòng liên hệ Admin nạp thêm hoặc thử lại sau ít phút!"
                    })
                    return

                # Trừ tiền khách trước
                new_balance = db.adjust_user_balance(user["id"], -cost)

                req_payload = {
                    "model": GROK_MODEL_SLUG,
                    "input": {
                        "prompt": prompt,
                        "mode": "image",
                        "image_urls": [image_url],
                        "aspect_ratio": aspect_ratio,
                        "resolution": "1080p",
                        "duration": grok_duration,
                        "n": "1",
                    }
                }

                last_err = "Không thể tạo Grok Video lúc này"
                for k in candidates:
                    st_code, cdata = cinai_json_request("POST", "/calls", k["api_key"], req_payload, timeout=60)
                    call_obj = None
                    if isinstance(cdata, dict):
                        call_obj = (cdata.get("data") or {}).get("call") if isinstance(cdata.get("data"), dict) else cdata.get("call")
                    if st_code in (200, 201, 202) and isinstance(call_obj, dict) and call_obj.get("id"):
                        call_id = str(call_obj["id"])
                        # Đánh dấu bỏ luôn key này sau khi đã dùng 15 credits cho 1 video
                        db.mark_grok_key_status(k["id"], "used", f"Đã dùng ({grok_duration}s) - Tự động bỏ")
                        db.add_grok_video(user["id"], call_id, f"[Grok {grok_duration}s] {prompt}", cost, k["api_key"])
                        self.send_json(200, {
                            "success": True,
                            "callId": call_id,
                            "remainingBalance": new_balance,
                        })
                        return

                    # Nếu key lỗi hoặc không đủ credit -> đánh dấu loại bỏ key đó và thử key kế tiếp
                    err_txt = str(cdata).lower()
                    if st_code in (401, 402, 403) or "credit" in err_txt or "insufficient" in err_txt or "unauthorized" in err_txt or "invalid" in err_txt:
                        db.mark_grok_key_status(k["id"], "invalid", f"Lỗi key (HTTP {st_code})")
                        last_err = f"Key hết hạn hoặc không đủ 15 credits (HTTP {st_code})"
                        continue
                    else:
                        last_err = (cdata.get("error") if isinstance(cdata, dict) else None) or f"Lỗi máy chủ Grok (HTTP {st_code})"
                        break

                # Hoàn tiền ngay nếu không tạo được video
                db.adjust_user_balance(user["id"], cost)
                self.send_json(500, {"success": False, "error": str(last_err)})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        # API ADMIN: Nạp / Cộng / Trừ tiền khách hàng (/api/admin/users/adjust-balance)
        if path == "/api/admin/users/adjust-balance":
            if not self.is_admin_authenticated():
                self.send_json(401, {"success": False, "error": "Yêu cầu quyền Quản trị viên!"})
                return
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body.decode("utf-8"))
                user_id = data.get("userId")
                amount = int(data.get("amount", 0))
                action = data.get("action", "add")

                if not user_id or amount <= 0:
                    self.send_json(400, {"success": False, "error": "Dữ liệu không hợp lệ!"})
                    return

                diff = amount if action == "add" else -amount
                new_bal = db.adjust_user_balance(user_id, diff)

                if new_bal is None:
                    self.send_json(404, {"success": False, "error": "Không tìm thấy khách hàng!"})
                    return

                self.send_json(200, {"success": True, "newBalance": new_bal})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        # API: ĐĂNG KÝ TÀI KHOẢN MỚI
        if path == "/api/auth/register":
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body.decode("utf-8"))
                username = data.get("username", "").strip()
                email = data.get("email", "").strip()
                password = data.get("password", "")

                if not username or not email or not password:
                    self.send_json(400, {"success": False, "error": "Vui lòng điền đủ tên đăng nhập, email và mật khẩu!"})
                    return

                if len(password) < 6:
                    self.send_json(400, {"success": False, "error": "Mật khẩu tối thiểu phải từ 6 ký tự!"})
                    return

                # Kiểm tra trùng lặp
                if db.find_user_by_login(username) or db.find_user_by_login(email):
                    self.send_json(400, {"success": False, "error": "Tên đăng nhập hoặc Email này đã được sử dụng!"})
                    return

                # Khách mới đăng ký: số dư = 0đ (bắt buộc nạp tiền mới được tạo video, chống spam SLL)
                initial_balance = 0 
                pwd_hash = hash_password(password)
                user = db.create_user(username, email, pwd_hash, initial_balance)

                # Tạo session token
                token = str(uuid.uuid4())
                db.create_session(token, user["id"])

                self.send_json(200, {
                    "success": True,
                    "token": token,
                    "user": {"id": user["id"], "username": username, "email": email, "balance": initial_balance}
                })
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        # API: ĐĂNG NHẬP
        if path == "/api/auth/login":
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body.decode("utf-8"))
                username = data.get("username", "").strip()
                password = data.get("password", "")

                if not username or not password:
                    self.send_json(400, {"success": False, "error": "Vui lòng nhập tên đăng nhập và mật khẩu!"})
                    return

                pwd_hash = hash_password(password)
                user = db.find_user_by_login(username)
                if not user or user.get("password_hash") != pwd_hash:
                    self.send_json(400, {"success": False, "error": "Tên đăng nhập hoặc mật khẩu không chính xác!"})
                    return

                token = str(uuid.uuid4())
                db.create_session(token, user["id"])

                self.send_json(200, {
                    "success": True,
                    "token": token,
                    "user": {"id": user["id"], "username": user["username"], "email": user["email"], "balance": user["balance"]}
                })
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        # API: ĐĂNG XUẤT
        if path == "/api/auth/logout":
            auth_header = self.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1].strip()
                db.delete_session(token)
            self.send_json(200, {"success": True})
            return

        # API: TẠO VIDEO (CÓ KIỂM TRA & TRỪ TIỀN KHÁCH HÀNG)
        if path == "/api/create-video":
            user = self.get_authenticated_user()
            if not user:
                self.send_json(401, {"success": False, "error": "AUTH_REQUIRED", "message": "Vui lòng đăng nhập hoặc tạo tài khoản trước khi tạo video!"})
                return

            body = self.rfile.read(content_length)
            try:
                req_data = json.loads(body.decode("utf-8"))
                model = req_data.get("model", "4.0-flash")
                duration = int(req_data.get("durationSeconds", 5))
                is_motion = bool(req_data.get("motionVideoObjectKey"))

                # Tính giá bán lẻ cho khách (Gấp đôi giá gốc để có lợi nhuận)
                cost = get_customer_price(model, duration, is_motion)

                # Kiểm tra số dư của khách hàng
                if user["balance"] < cost:
                    self.send_json(402, {
                        "success": False,
                        "error": "INSUFFICIENT_BALANCE",
                        "message": f"Số dư của bạn không đủ ({user['balance']} đ). Lượt này cần {cost} đ. Vui lòng nạp thêm tiền để tiếp tục!"
                    })
                    return

                # Trừ tiền tài khoản của khách trước
                new_balance = db.adjust_user_balance(user["id"], -cost)

                # Chuẩn bị payload gửi sang Klinggiare
                batch_payload = {
                    "prompt": req_data.get("prompt") or "Video chất lượng cao",
                    "settings": {
                        "model": model,
                        "durationSeconds": duration,
                        "aspectRatio": req_data.get("aspectRatio", "16:9"),
                        "resolution": "720p",
                        "audio": bool(req_data.get("audio", True))
                    }
                }
                
                if req_data.get("imageKeys"):
                    batch_payload["imageKeys"] = req_data.get("imageKeys")
                if req_data.get("endFrameKey"):
                    batch_payload["endFrameKey"] = req_data.get("endFrameKey")

                # TỰ ĐỘNG HIỆU CHỈNH THÔNG SỐ ĐẢM BẢO KHÔNG BỊ LỖI API:
                if is_motion:
                    batch_payload["jobType"] = "motion_control"
                    batch_payload["motionVideoObjectKey"] = req_data.get("motionVideoObjectKey")
                    batch_payload["keepOriginalSound"] = req_data.get("keepOriginalSound", True)
                    batch_payload["settings"]["model"] = "2.6"
                    batch_payload["settings"]["durationSeconds"] = 0
                else:
                    # Model 4.0 Pro cố định 5s
                    if model == "4.0":
                        batch_payload["settings"]["durationSeconds"] = 5
                    # Model 3.0 cố định 10s
                    elif model == "3.0":
                        batch_payload["settings"]["durationSeconds"] = 10

                    # Model 2.6 và 3.0 KHÔNG hỗ trợ audio=True (Kling API từ chối nếu gửi audio=true)
                    if model in ["2.6", "3.0"]:
                        batch_payload["settings"]["audio"] = False

                    # Model 2.1 chỉ hỗ trợ Ảnh sang Video
                    if model == "2.1" and not req_data.get("imageKeys"):
                        db.adjust_user_balance(user["id"], cost)
                        self.send_json(400, {
                            "success": False,
                            "error": "Mô hình Kling 2.1 chỉ hỗ trợ chế độ 'Ảnh Sang Video'. Vui lòng chọn tab Ảnh Sang Video hoặc chuyển sang Kling 4.0 Flash."
                        })
                        return

                idempotency_key = str(uuid.uuid4())

                # Gọi API Klinggiare
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
                
                try:
                    with urllib.request.urlopen(req, timeout=15) as res:
                        batch_data = json.loads(res.read().decode("utf-8"))
                        jobs = batch_data.get("jobs", [])
                        job_id = jobs[0].get("id") if jobs else None
                        
                        # Lưu lịch sử tạo video vào DB đám mây
                        db.add_user_video(user["id"], job_id, batch_payload["prompt"], cost, "processing")

                        self.send_json(200, {
                            "success": True, 
                            "batch": batch_data,
                            "jobId": job_id,
                            "remainingBalance": new_balance
                        })
                except Exception as api_err:
                    # NẾU API LỖI -> HOÀN LẠI TIỀN CHO KHÁCH NGAY LẬP TỨC!
                    db.adjust_user_balance(user["id"], cost)
                    raise api_err

            except urllib.error.HTTPError as e:
                self.send_json(e.code, {"success": False, "error": e.read().decode("utf-8")})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        # API: Tải ảnh/video lên Klinggiare (Dùng cơ chế 3 bước Presigned R2 chuẩn như trang chủ Klinggiare)
        if path == "/api/upload-image":
            content_type = self.headers.get("Content-Type", "")
            body = self.rfile.read(content_length)
            try:
                m = re.search(r"boundary=([^;\s]+)", content_type)
                if not m:
                    raise ValueError("Missing multipart boundary")
                boundary = m.group(1).strip('"').encode("utf-8")
                parts = body.split(b"--" + boundary)
                upload_res = None

                for part in parts:
                    if b"Content-Disposition" not in part:
                        continue
                    part = part.lstrip(b"\r\n")
                    if b"\r\n\r\n" not in part:
                        continue
                    header_bytes, file_bytes = part.split(b"\r\n\r\n", 1)
                    if file_bytes.endswith(b"\r\n"):
                        file_bytes = file_bytes[:-2]
                    header_str = header_bytes.decode("utf-8", errors="ignore")
                    fn_match = re.search(r'filename="([^"]+)"', header_str)
                    filename = fn_match.group(1) if fn_match else "upload.mp4"
                    ct_match = re.search(r"Content-Type:\s*([^\r\n]+)", header_str, re.IGNORECASE)
                    part_ct = ct_match.group(1).strip().lower() if ct_match else ""

                    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
                    if file_bytes.startswith(b"\xff\xd8\xff"):
                        mime = "image/jpeg"
                    elif file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                        mime = "image/png"
                    elif file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
                        mime = "image/webp"
                    elif file_bytes.startswith((b"GIF87a", b"GIF89a")):
                        mime = "image/gif"
                    elif file_bytes.startswith(b"\x1a\x45\xdf\xa3"):
                        mime = "video/webm"
                    elif len(file_bytes) >= 12 and file_bytes[4:8] in (b"ftyp", b"moov", b"wide", b"mdat"):
                        if ext == "mov" or file_bytes[8:12] == b"qt  ":
                            mime = "video/quicktime"
                        else:
                            mime = "video/mp4"
                    elif ext in ("jpg", "jpeg"):
                        mime = "image/jpeg"
                    elif ext == "png":
                        mime = "image/png"
                    elif ext == "webp":
                        mime = "image/webp"
                    elif ext == "gif":
                        mime = "image/gif"
                    elif ext == "mov":
                        mime = "video/quicktime"
                    elif ext == "webm":
                        mime = "video/webm"
                    elif ext in ("mp4", "m4v", "3gp", "mov"):
                        mime = "video/mp4"
                    elif part_ct in ("image/jpeg", "image/png", "image/webp", "image/gif", "video/mp4", "video/quicktime", "video/webm"):
                        mime = part_ct
                    else:
                        mime = "video/mp4" if "video" in part_ct else "image/jpeg"

                    # Bước 1: Lấy Presigned Upload URL từ Klinggiare
                    init_payload = {
                        "files": [{
                            "filename": filename,
                            "contentType": mime,
                            "sizeBytes": len(file_bytes)
                        }]
                    }
                    req1 = urllib.request.Request(
                        f"{API_BASE}/api/v1/ext/batches/uploads/init",
                        data=json.dumps(init_payload).encode("utf-8"),
                        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
                    )
                    with urllib.request.urlopen(req1, timeout=30) as res1:
                        init_data = json.loads(res1.read().decode("utf-8"))
                        item = init_data["items"][0]

                    # Bước 2: PUT trực tiếp dữ liệu file lên kho lưu trữ Cloudflare R2
                    req2 = urllib.request.Request(
                        item["uploadUrl"],
                        data=file_bytes,
                        headers={"Content-Type": item["contentType"], "User-Agent": "Mozilla/5.0"},
                        method="PUT"
                    )
                    with urllib.request.urlopen(req2, timeout=180) as res2:
                        _ = res2.read()

                    # Bước 3: Xác nhận hoàn tất upload (uploads/complete)
                    comp_payload = {"items": [{"objectKey": item["objectKey"]}]}
                    req3 = urllib.request.Request(
                        f"{API_BASE}/api/v1/ext/batches/uploads/complete",
                        data=json.dumps(comp_payload).encode("utf-8"),
                        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
                    )
                    with urllib.request.urlopen(req3, timeout=30) as res3:
                        upload_res = json.loads(res3.read().decode("utf-8"))
                    break

                if not upload_res:
                    raise ValueError("Không tìm thấy dữ liệu tệp tải lên")

                self.send_json(200, {"success": True, "data": upload_res})
            except urllib.error.HTTPError as e:
                err_text = e.read().decode("utf-8")
                try:
                    err_json = json.loads(err_text)
                    err_msg = err_json.get("error", {}).get("message") or err_text
                except Exception:
                    err_msg = err_text
                self.send_json(e.code, {"success": False, "error": err_msg})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        self.send_json(404, {"error": "Not Found"})

def run():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), KlingHandler) as httpd:
        print(f"🚀 XENOECOM KLING AI WEB SERVER DANG CHAY TAI:")
        print(f"👉 http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nDa dung server.")

if __name__ == "__main__":
    run()
