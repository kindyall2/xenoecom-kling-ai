"""
Database Layer for Kling AI Web - Xenoecom Studio
Hỗ trợ cả Supabase Cloud Database (Vĩnh Viễn) và SQLite (Local Fallback)
"""

import os
import sqlite3
import json
import time
import urllib.request
import urllib.error

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://zcydimrutzdajwcbcrzh.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpjeWRpbXJ1dHpkYWp3Y2JjcnpoIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc5NDg0MjA0OCwiZXhwIjoyMTEwNDE4MDQ4fQ.Uv2Znb5Qef8KPMkR4iwF4398pofmzkvdnW5aj1llYss")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.db")

def is_supabase_enabled():
    return bool(SUPABASE_URL and SUPABASE_KEY)

def s_req(path, method="GET", data=None, extra_headers=None):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    if extra_headers:
        headers.update(extra_headers)
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1/{path}", data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as res:
        content = res.read().decode("utf-8")
        return json.loads(content) if content else None

def get_sqlite():
    conn = sqlite3.connect(DB_PATH)
    return conn

def init_db():
    conn = get_sqlite()
    c = conn.cursor()
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
    c.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at INTEGER NOT NULL
    )
    """)
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

# 1. Tìm user theo username hoặc email
def find_user_by_login(identifier):
    identifier = identifier.strip()
    if is_supabase_enabled():
        try:
            # ilike tìm kiếm không phân biệt hoa thường
            q = f"users?or=(username.ilike.{identifier},email.ilike.{identifier})&select=*"
            res = s_req(q)
            return res[0] if res else None
        except Exception as e:
            print("[DB] Supabase find_user_by_login error:", e)
    
    conn = get_sqlite()
    c = conn.cursor()
    c.execute("SELECT id, username, email, password_hash, balance, created_at FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)", (identifier, identifier))
    row = c.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "username": row[1], "email": row[2], "password_hash": row[3], "balance": row[4], "created_at": row[5]}
    return None

# 2. Tạo user mới
def create_user(username, email, password_hash, initial_balance=0):
    username = username.strip()
    email = email.strip()
    if is_supabase_enabled():
        try:
            payload = {
                "username": username,
                "email": email,
                "password_hash": password_hash,
                "balance": initial_balance
            }
            res = s_req("users", method="POST", data=payload, extra_headers={"Prefer": "return=representation"})
            if res and len(res) > 0:
                return res[0]
        except Exception as e:
            print("[DB] Supabase create_user error:", e)
    
    conn = get_sqlite()
    c = conn.cursor()
    c.execute("INSERT INTO users (username, email, password_hash, balance) VALUES (?, ?, ?, ?)",
              (username, email, password_hash, initial_balance))
    user_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"id": user_id, "username": username, "email": email, "balance": initial_balance}

# 3. Quản lý Session
def create_session(token, user_id):
    if is_supabase_enabled():
        try:
            s_req("sessions", method="POST", data={"token": token, "user_id": user_id, "created_at": int(time.time())})
            return True
        except Exception as e:
            print("[DB] Supabase create_session error:", e)
    
    conn = get_sqlite()
    c = conn.cursor()
    c.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)", (token, user_id, int(time.time())))
    conn.commit()
    conn.close()
    return True

def get_user_by_session_token(token):
    if not token:
        return None
    token = token.strip()
    if is_supabase_enabled():
        try:
            q = f"sessions?token=eq.{token}&select=token,user_id,users(id,username,email,balance)"
            res = s_req(q)
            if res and len(res) > 0 and res[0].get("users"):
                u = res[0]["users"]
                return {"id": u["id"], "username": u["username"], "email": u["email"], "balance": u["balance"], "token": token}
        except Exception as e:
            print("[DB] Supabase get_user_by_session_token error:", e)
    
    conn = get_sqlite()
    c = conn.cursor()
    c.execute("SELECT users.id, users.username, users.email, users.balance FROM sessions JOIN users ON sessions.user_id = users.id WHERE sessions.token = ?", (token,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "username": row[1], "email": row[2], "balance": row[3], "token": token}
    return None

def delete_session(token):
    if is_supabase_enabled():
        try:
            s_req(f"sessions?token=eq.{token}", method="DELETE")
            return True
        except Exception as e:
            print("[DB] Supabase delete_session error:", e)
    conn = get_sqlite()
    c = conn.cursor()
    c.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()
    return True

# 4. Quản lý số dư (Balance)
def adjust_user_balance(user_id, amount_diff):
    if is_supabase_enabled():
        try:
            # Lấy balance hiện tại
            u_res = s_req(f"users?id=eq.{user_id}&select=balance")
            if u_res and len(u_res) > 0:
                current_bal = int(u_res[0].get("balance", 0))
                new_bal = max(0, current_bal + amount_diff)
                up_res = s_req(f"users?id=eq.{user_id}", method="PATCH", data={"balance": new_bal}, extra_headers={"Prefer": "return=representation"})
                if up_res and len(up_res) > 0:
                    return new_bal
        except Exception as e:
            print("[DB] Supabase adjust_user_balance error:", e)

    conn = get_sqlite()
    c = conn.cursor()
    c.execute("UPDATE users SET balance = MAX(0, balance + ?) WHERE id = ?", (amount_diff, user_id))
    c.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.commit()
    conn.close()
    return row[0] if row else None

# 5. Lịch sử Video của người dùng
def add_user_video(user_id, job_id, prompt, cost, status="processing"):
    if is_supabase_enabled():
        try:
            payload = {
                "user_id": user_id,
                "job_id": job_id,
                "prompt": prompt,
                "cost": cost,
                "status": status
            }
            s_req("user_videos", method="POST", data=payload)
            return True
        except Exception as e:
            print("[DB] Supabase add_user_video error:", e)
    
    conn = get_sqlite()
    c = conn.cursor()
    c.execute("INSERT INTO user_videos (user_id, job_id, prompt, cost, status) VALUES (?, ?, ?, ?, ?)",
              (user_id, job_id, prompt, cost, status))
    conn.commit()
    conn.close()
    return True

def update_video_url(job_id, video_url):
    if is_supabase_enabled():
        try:
            s_req(f"user_videos?job_id=eq.{job_id}", method="PATCH", data={"video_url": video_url, "status": "success"})
            return True
        except Exception as e:
            print("[DB] Supabase update_video_url error:", e)

    conn = get_sqlite()
    c = conn.cursor()
    c.execute("UPDATE user_videos SET video_url = ?, status = 'success' WHERE job_id = ?", (video_url, job_id))
    conn.commit()
    conn.close()
    return True

def get_user_videos(user_id, limit=20):
    if is_supabase_enabled():
        try:
            q = f"user_videos?user_id=eq.{user_id}&order=id.desc&limit={limit}&select=job_id,prompt,video_url,cost,status,created_at"
            rows = s_req(q)
            if rows is not None:
                return [{"jobId": r["job_id"], "prompt": r["prompt"], "videoUrl": r["video_url"], "cost": r["cost"], "status": r["status"], "time": r["created_at"]} for r in rows]
        except Exception as e:
            print("[DB] Supabase get_user_videos error:", e)

    conn = get_sqlite()
    c = conn.cursor()
    c.execute("SELECT job_id, prompt, video_url, cost, status, created_at FROM user_videos WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [{"jobId": r[0], "prompt": r[1], "videoUrl": r[2], "cost": r[3], "status": r[4], "time": r[5]} for r in rows]

# 6. Các hàm dành cho Admin
def get_admin_stats():
    if is_supabase_enabled():
        try:
            users = s_req("users?select=id,balance") or []
            total_users = len(users)
            total_user_balance = sum(int(u.get("balance") or 0) for u in users)
            vids = s_req("user_videos?status=eq.success&select=id") or []
            total_videos = len(vids)
            return total_users, total_user_balance, total_videos
        except Exception as e:
            print("[DB] Supabase get_admin_stats error:", e)

    conn = get_sqlite()
    c = conn.cursor()
    c.execute("SELECT COUNT(*), COALESCE(SUM(balance), 0) FROM users")
    total_users, total_user_balance = c.fetchone()
    c.execute("SELECT COUNT(*) FROM user_videos WHERE status = 'success'")
    total_videos = c.fetchone()[0]
    conn.close()
    return total_users, total_user_balance, total_videos

def get_admin_users():
    if is_supabase_enabled():
        try:
            users = s_req("users?select=id,username,email,balance,created_at&order=id.desc") or []
            vids = s_req("user_videos?status=eq.success&select=user_id") or []
            counts = {}
            for v in vids:
                uid = v.get("user_id")
                counts[uid] = counts.get(uid, 0) + 1
            for u in users:
                u["videoCount"] = counts.get(u["id"], 0)
            return users
        except Exception as e:
            print("[DB] Supabase get_admin_users error:", e)

    conn = get_sqlite()
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
    return [
        {"id": r[0], "username": r[1], "email": r[2], "balance": r[3], "created_at": r[4], "videoCount": r[5]}
        for r in rows
    ]

def get_admin_videos(limit=40):
    if is_supabase_enabled():
        try:
            q = f"user_videos?select=prompt,video_url,cost,created_at,users(username)&video_url=not.is.null&order=id.desc&limit={limit}"
            vids = s_req(q) or []
            result = []
            for v in vids:
                username = v.get("users", {}).get("username") if isinstance(v.get("users"), dict) else "Khách"
                result.append({
                    "username": username,
                    "prompt": v.get("prompt"),
                    "videoUrl": v.get("video_url"),
                    "cost": v.get("cost"),
                    "time": v.get("created_at")
                })
            return result
        except Exception as e:
            print("[DB] Supabase get_admin_videos error:", e)

    conn = get_sqlite()
    c = conn.cursor()
    c.execute("""
        SELECT u.username, v.prompt, v.video_url, v.cost, v.created_at
        FROM user_videos v
        JOIN users u ON v.user_id = u.id
        WHERE v.video_url IS NOT NULL AND v.video_url != ''
        ORDER BY v.id DESC LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return [{"username": r[0], "prompt": r[1], "videoUrl": r[2], "cost": r[3], "time": r[4]} for r in rows]

init_db()
