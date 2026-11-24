#!/usr/bin/env python3
"""
無人機練習紀錄系統 - 後端
只用 Python 標準函式庫（不需要安裝任何套件），資料存在 SQLite。

環境變數：
  PORT        監聽埠號（預設 8080）
  DATA_DIR    資料庫存放資料夾（預設 ./data）
  ADMIN_PIN   老師管理密碼（新增/修改學生、刪除紀錄時需要；預設 1234，請務必修改）
"""
import csv
import io
import json
import os
import re
import sqlite3
import threading
from datetime import date, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("PORT", "8080"))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
ADMIN_PIN = os.environ.get("ADMIN_PIN", "1234")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
DB_PATH = os.path.join(DATA_DIR, "drone.db")
MODES = ("attack", "chase", "keeper")

os.makedirs(DATA_DIR, exist_ok=True)
_lock = threading.Lock()


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                team TEXT DEFAULT '',
                role TEXT DEFAULT '',
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                date TEXT NOT NULL,
                mode TEXT NOT NULL CHECK (mode IN ('attack','chase','keeper')),
                value REAL NOT NULL,
                time_limit INTEGER,
                note TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_records_student ON records(student_id, mode, date);
            """
        )


class ApiError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status = status
        self.msg = msg


def valid_date(s):
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


class Handler(SimpleHTTPRequestHandler):
    server_version = "DronePractice/1.0"

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=STATIC_DIR, **kw)

    def end_headers(self):
        # 網頁、App 檔案每次都向伺服器確認是否有新版（避免 Cloudflare 或手機快取舊版）
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")
            if self.path.split("?")[0].endswith("sw.js"):
                self.send_header("Service-Worker-Allowed", "/")
        super().end_headers()

    def log_message(self, fmt, *args):
        print("[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), fmt % args))

    # ---------- helpers ----------
    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def body_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 100_000:
            raise ApiError(413, "資料太大")
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            raise ApiError(400, "JSON 格式錯誤")

    def require_pin(self):
        if ADMIN_PIN and self.headers.get("X-Admin-Pin", "") != ADMIN_PIN:
            raise ApiError(403, "需要老師管理密碼")

    def route(self, method):
        url = urlparse(self.path)
        if not url.path.startswith("/api/"):
            return False
        try:
            self.dispatch(method, url.path, parse_qs(url.query))
        except ApiError as e:
            self.send_json({"error": e.msg}, e.status)
        except sqlite3.IntegrityError as e:
            msg = "名字重複了" if "UNIQUE" in str(e) else "資料不正確"
            self.send_json({"error": msg}, 400)
        except Exception as e:  # noqa
            self.log_message("ERROR %s", e)
            self.send_json({"error": "伺服器錯誤"}, 500)
        return True

    # ---------- HTTP verbs ----------
    def do_GET(self):
        if not self.route("GET"):
            if self.path in ("/", "") or self.path.startswith("/?"):
                self.path = "/index.html"
            super().do_GET()

    def do_POST(self):
        if not self.route("POST"):
            self.send_error(404)

    def do_PUT(self):
        if not self.route("PUT"):
            self.send_error(404)

    def do_DELETE(self):
        if not self.route("DELETE"):
            self.send_error(404)

    # ---------- API ----------
    def dispatch(self, method, path, q):
        m = re.fullmatch(r"/api/(\w+)(?:/(\d+))?(\.csv)?", path)
        if not m:
            raise ApiError(404, "找不到")
        res, rid, csv_ext = m.group(1), m.group(2), m.group(3)
        rid = int(rid) if rid else None

        if res == "ping" and method == "GET":
            return self.send_json({"ok": True, "pin_required": bool(ADMIN_PIN)})

        if res == "check_pin" and method == "POST":
            self.require_pin()
            return self.send_json({"ok": True})

        if res == "students":
            return self.students(method, rid)

        if res == "records":
            return self.records(method, rid, q)

        if res == "export" and csv_ext and method == "GET":
            return self.export_csv()

        raise ApiError(404, "找不到")

    def students(self, method, rid):
        with _lock, db() as c:
            if method == "GET":
                rows = c.execute("SELECT * FROM students ORDER BY active DESC, team, name").fetchall()
                return self.send_json([dict(r) for r in rows])
            self.require_pin()
            if method == "POST":
                d = self.body_json()
                name = (d.get("name") or "").strip()
                if not name:
                    raise ApiError(400, "請輸入名字")
                cur = c.execute(
                    "INSERT INTO students(name, team, role) VALUES (?,?,?)",
                    (name, (d.get("team") or "").strip(), (d.get("role") or "").strip()),
                )
                return self.send_json({"id": cur.lastrowid}, 201)
            if method == "PUT" and rid:
                d = self.body_json()
                old = c.execute("SELECT * FROM students WHERE id=?", (rid,)).fetchone()
                if not old:
                    raise ApiError(404, "找不到學生")
                c.execute(
                    "UPDATE students SET name=?, team=?, role=?, active=? WHERE id=?",
                    (
                        (d.get("name") or old["name"]).strip(),
                        d.get("team", old["team"]),
                        d.get("role", old["role"]),
                        int(d.get("active", old["active"])),
                        rid,
                    ),
                )
                return self.send_json({"ok": True})
            if method == "DELETE" and rid:
                c.execute("DELETE FROM students WHERE id=?", (rid,))
                return self.send_json({"ok": True})
        raise ApiError(405, "不支援")

    def records(self, method, rid, q):
        with _lock, db() as c:
            if method == "GET":
                sql = "SELECT r.*, s.name AS student_name FROM records r JOIN students s ON s.id=r.student_id WHERE 1=1"
                args = []
                if q.get("student_id"):
                    sql += " AND r.student_id=?"
                    args.append(int(q["student_id"][0]))
                if q.get("mode"):
                    sql += " AND r.mode=?"
                    args.append(q["mode"][0])
                if q.get("from"):
                    sql += " AND r.date>=?"
                    args.append(q["from"][0])
                if q.get("to"):
                    sql += " AND r.date<=?"
                    args.append(q["to"][0])
                sql += " ORDER BY r.date, r.id"
                return self.send_json([dict(r) for r in c.execute(sql, args).fetchall()])
            if method == "POST":
                d = self.body_json()
                mode = d.get("mode")
                if mode not in MODES:
                    raise ApiError(400, "模式不正確")
                dt = d.get("date") or date.today().isoformat()
                if not valid_date(dt):
                    raise ApiError(400, "日期格式不正確")
                try:
                    value = float(d.get("value"))
                    sid = int(d.get("student_id"))
                except (TypeError, ValueError):
                    raise ApiError(400, "請選學生並輸入成績")
                if value < 0 or value > 100000:
                    raise ApiError(400, "成績數字不合理")
                tl = d.get("time_limit")
                tl = int(tl) if (tl not in (None, "") and mode != "keeper") else None
                if not c.execute("SELECT 1 FROM students WHERE id=?", (sid,)).fetchone():
                    raise ApiError(400, "找不到這位學生")
                cur = c.execute(
                    "INSERT INTO records(student_id, date, mode, value, time_limit, note) VALUES (?,?,?,?,?,?)",
                    (sid, dt, mode, value, tl, (d.get("note") or "").strip()[:200]),
                )
                return self.send_json({"id": cur.lastrowid}, 201)
            if method == "DELETE" and rid:
                self.require_pin()
                c.execute("DELETE FROM records WHERE id=?", (rid,))
                return self.send_json({"ok": True})
        raise ApiError(405, "不支援")

    def export_csv(self):
        with _lock, db() as c:
            rows = c.execute(
                "SELECT r.date, s.name, s.team, s.role, r.mode, r.value, r.time_limit, r.note, r.created_at "
                "FROM records r JOIN students s ON s.id=r.student_id ORDER BY r.date, s.name"
            ).fetchall()
        names = {"attack": "進攻", "chase": "防守追球", "keeper": "防守守門"}
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["日期", "學生", "隊伍", "位置", "模式", "成績", "限時(秒)", "備註", "登錄時間"])
        for r in rows:
            w.writerow([r[0], r[1], r[2], r[3], names.get(r[4], r[4]), r[5], r[6] or "", r[7], r[8]])
        body = ("﻿" + buf.getvalue()).encode("utf-8")  # BOM 讓 Excel 正確顯示中文
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="drone_records_%s.csv"' % date.today().isoformat())
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    init_db()
    print(f"無人機練習紀錄系統啟動：http://0.0.0.0:{PORT}  (資料庫：{DB_PATH})")
    if ADMIN_PIN == "1234":
        print("⚠️  目前使用預設管理密碼 1234，請設定環境變數 ADMIN_PIN 修改")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
