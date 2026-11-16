"""
Kling AI Video Generator Backend - Xenoecom Studio
Hệ thống kết nối Klinggiare API + Quản lý Tài khoản & Số dư Khách hàng (SQLite) + Quản trị Admin
Không yêu cầu cài thêm thư viện (chạy 100% bằng Python tiêu chuẩn)
"""

import http.server
import socketserver
import json
import urllib.request
import urllib.error
import uuid
import os
import sqlite3
import hashlib
import time

PORT = int(os.environ.get("PORT", 8080))
API_BASE = "https://klinggiare.com"
API_KEY = os.environ.get("KLING_API_KEY", "kling_sk_6bV7-Nvtk9GruKUDL-uMl0OfUXQEldZt_3lQF0MyLhE")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "xenoecom@admin2026")
ADMIN_TOKENS = set()

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.db")

# Khởi tạo Cơ sở dữ liệu SQLite
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Bảng người dùng
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        balance INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    # Bảng phiên đăng nhập (Sessions)
    c.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    # Bảng lịch sử video của khách
    c.execute("""
    CREATE TABLE IF NOT EXISTS user_videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        job_id INTEGER,
        prompt TEXT,
        video_url TEXT,
        cost INTEGER,
        status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

init_db()

def hash_password(password):
    return hashlib.sha256(("xenoecom_salt_" + password).encode("utf-8")).hexdigest()

def get_db():
    return sqlite3.connect(DB_PATH)

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
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT users.id, users.username, users.email, users.balance FROM sessions JOIN users ON sessions.user_id = users.id WHERE sessions.token = ?", (token,))
        row = c.fetchone()
        conn.close()
        if row:
            return {"id": row[0], "username": row[1], "email": row[2], "balance": row[3], "token": token}
        return None

    def is_admin_authenticated(self):
        token = self.headers.get("X-Admin-Token", "").strip()
        return bool(token and token in ADMIN_TOKENS)

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
                conn = get_db()
                c = conn.cursor()
                c.execute("SELECT COUNT(*), COALESCE(SUM(balance), 0) FROM users")
                total_users, total_user_balance = c.fetchone()
                c.execute("SELECT COUNT(*) FROM user_videos WHERE status = 'success'")
                total_videos = c.fetchone()[0]
                conn.close()

                # Lấy số dư ví Klinggiare gốc
                kling_balance = 0
                try:
                    req = urllib.request.Request(
                        f"{API_BASE}/api/v1/ext/wallet",
                        headers={"Authorization": f"Bearer {API_KEY}", "User-Agent": "Mozilla/5.0"}
                    )
                    with urllib.request.urlopen(req, timeout=8) as res:
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
                conn = get_db()
                c = conn.cursor()
                c.execute("""
                    SELECT u.id, u.username, u.email, u.balance, u.created_at, COUNT(v.id) as video_count
                    FROM users u
                    LEFT JOIN user_videos v ON u.id = v.user_id AND v.status = 'success'
                    GROUP BY u.id
                    ORDER BY u.id DESC
                """)
                rows = c.fetchall()
                conn.close()
                user_list = [
                    {
                        "id": r[0],
                        "username": r[1],
                        "email": r[2],
                        "balance": r[3],
                        "created_at": r[4],
                        "videoCount": r[5]
                    }
                    for r in rows
                ]
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
                conn = get_db()
                c = conn.cursor()
                c.execute("""
                    SELECT u.username, v.prompt, v.video_url, v.cost, v.created_at
                    FROM user_videos v
                    JOIN users u ON v.user_id = u.id
                    WHERE v.video_url IS NOT NULL AND v.video_url != ''
                    ORDER BY v.id DESC LIMIT 40
                """)
                rows = c.fetchall()
                conn.close()
                vid_list = [
                    {
                        "username": r[0],
                        "prompt": r[1],
                        "videoUrl": r[2],
                        "cost": r[3],
                        "time": r[4]
                    }
                    for r in rows
                ]
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

        # API: Lấy lịch sử video của khách
        if path == "/api/user/videos":
            user = self.get_authenticated_user()
            if not user:
                self.send_json(401, {"success": False, "error": "Chưa đăng nhập"})
                return
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT job_id, prompt, video_url, cost, status, created_at FROM user_videos WHERE user_id = ? ORDER BY id DESC LIMIT 20", (user["id"],))
            rows = c.fetchall()
            conn.close()
            videos = [{"jobId": r[0], "prompt": r[1], "videoUrl": r[2], "cost": r[3], "status": r[4], "time": r[5]} for r in rows]
            self.send_json(200, {"success": True, "videos": videos})
            return

        # API: Kiểm tra trạng thái bảo trì hệ thống
        if path == "/api/system/status":
            try:
                req = urllib.request.Request(
                    f"{API_BASE}/api/v1/system/status",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=10) as res:
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
                            conn = get_db()
                            c = conn.cursor()
                            c.execute("UPDATE user_videos SET video_url = ?, status = 'success' WHERE job_id = ?", (video_url, job_id))
                            conn.commit()
                            conn.close()

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
                    token = "xenoecom_adm_" + str(uuid.uuid4())
                    ADMIN_TOKENS.add(token)
                    self.send_json(200, {"success": True, "adminToken": token})
                else:
                    self.send_json(400, {"success": False, "error": "Mật khẩu Quản trị Admin không chính xác!"})
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
                conn = get_db()
                c = conn.cursor()
                c.execute("UPDATE users SET balance = MAX(0, balance + ?) WHERE id = ?", (diff, user_id))
                c.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
                row = c.fetchone()
                conn.commit()
                conn.close()

                if not row:
                    self.send_json(404, {"success": False, "error": "Không tìm thấy khách hàng!"})
                    return

                self.send_json(200, {"success": True, "newBalance": row[0]})
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

                conn = get_db()
                c = conn.cursor()
                # Kiểm tra trùng lặp
                c.execute("SELECT id FROM users WHERE username = ? OR email = ?", (username, email))
                if c.fetchone():
                    conn.close()
                    self.send_json(400, {"success": False, "error": "Tên đăng nhập hoặc Email này đã được sử dụng!"})
                    return

                # Khách mới đăng ký: số dư = 0đ (bắt buộc nạp tiền mới được tạo video, chống spam SLL)
                initial_balance = 0 
                pwd_hash = hash_password(password)
                c.execute("INSERT INTO users (username, email, password_hash, balance) VALUES (?, ?, ?, ?)",
                          (username, email, pwd_hash, initial_balance))
                user_id = c.lastrowid

                # Tạo session token
                token = str(uuid.uuid4())
                c.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
                          (token, user_id, int(time.time())))
                conn.commit()
                conn.close()

                self.send_json(200, {
                    "success": True,
                    "token": token,
                    "user": {"id": user_id, "username": username, "email": email, "balance": initial_balance}
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

                conn = get_db()
                c = conn.cursor()
                pwd_hash = hash_password(password)
                c.execute("SELECT id, username, email, balance FROM users WHERE (username = ? OR email = ?) AND password_hash = ?",
                          (username, username, pwd_hash))
                row = c.fetchone()
                if not row:
                    conn.close()
                    self.send_json(400, {"success": False, "error": "Tên đăng nhập hoặc mật khẩu không chính xác!"})
                    return

                user_id = row[0]
                token = str(uuid.uuid4())
                c.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
                          (token, user_id, int(time.time())))
                conn.commit()
                conn.close()

                self.send_json(200, {
                    "success": True,
                    "token": token,
                    "user": {"id": user_id, "username": row[1], "email": row[2], "balance": row[3]}
                })
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        # API: ĐĂNG XUẤT
        if path == "/api/auth/logout":
            auth_header = self.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1].strip()
                conn = get_db()
                c = conn.cursor()
                c.execute("DELETE FROM sessions WHERE token = ?", (token,))
                conn.commit()
                conn.close()
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
                conn = get_db()
                c = conn.cursor()
                new_balance = user["balance"] - cost
                c.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user["id"]))
                conn.commit()

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
                if is_motion:
                    batch_payload["jobType"] = "motion_control"
                    batch_payload["motionVideoObjectKey"] = req_data.get("motionVideoObjectKey")
                    batch_payload["keepOriginalSound"] = req_data.get("keepOriginalSound", True)
                    batch_payload["settings"]["model"] = "2.6"
                    batch_payload["settings"]["durationSeconds"] = 0

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
                        
                        # Lưu lịch sử tạo video vào DB
                        c.execute("INSERT INTO user_videos (user_id, job_id, prompt, cost, status) VALUES (?, ?, ?, ?, 'processing')",
                                  (user["id"], job_id, batch_payload["prompt"], cost))
                        conn.commit()
                        conn.close()

                        self.send_json(200, {
                            "success": True, 
                            "batch": batch_data,
                            "jobId": job_id,
                            "remainingBalance": new_balance
                        })
                except Exception as api_err:
                    # NẾU API LỖI -> HOÀN LẠI TIỀN CHO KHÁCH NGAY LẬP TỨC!
                    c.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (cost, user["id"]))
                    conn.commit()
                    conn.close()
                    raise api_err

            except urllib.error.HTTPError as e:
                self.send_json(e.code, {"success": False, "error": e.read().decode("utf-8")})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            return

        # API: Tải ảnh/video lên Klinggiare
        if path == "/api/upload-image":
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
        print(f"🚀 XENOECOM KLING AI WEB SERVER DANG CHAY TAI:")
        print(f"👉 http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("
Da dung server.")

if __name__ == "__main__":
    run()
