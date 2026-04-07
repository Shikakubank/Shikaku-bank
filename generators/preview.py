"""
ローカルプレビューサーバー
使い方: python generators/preview.py
ブラウザで http://localhost:8000 を開く
"""

import http.server
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError:
    print("Jinja2が見つかりません。pip install Jinja2 を実行してください。")
    sys.exit(1)

ROOT      = Path(__file__).parent.parent
DB_PATH   = ROOT / "data" / "courses.db"
TEMPLATES = ROOT / "templates"
OUTPUT    = ROOT / "output"

# ── Jinja2環境 ──────────────────────────
env = Environment(
    loader=FileSystemLoader(str(TEMPLATES)),
    autoescape=select_autoescape(["html"]),
)

def number_format(value):
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return value

def dateformat(value, fmt="%Y.%m.%d"):
    if not value:
        return ""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(str(value))
        return dt.strftime(fmt)
    except Exception:
        return str(value)

env.filters["number_format"] = number_format
env.filters["dateformat"]    = dateformat

# ── 共通コンテキスト ─────────────────────
NAV_CATEGORIES = [
    {"name": "IT・プログラミング", "slug": "it",         "icon": "💻"},
    {"name": "語学・英会話",       "slug": "english",    "icon": "🌍"},
    {"name": "会計・簿記",         "slug": "accounting", "icon": "📊"},
    {"name": "医療・介護",         "slug": "medical",    "icon": "🏥"},
    {"name": "不動産・宅建",       "slug": "estate",     "icon": "🏠"},
    {"name": "デザイン",           "slug": "design",     "icon": "🎨"},
    {"name": "法務・行政",         "slug": "legal",      "icon": "⚖️"},
    {"name": "経営・ビジネス",     "slug": "business",   "icon": "📈"},
]

NAV_AREAS = [
    {"name": "東京都", "slug": "tokyo"},
    {"name": "大阪府", "slug": "osaka"},
    {"name": "神奈川県", "slug": "kanagawa"},
    {"name": "愛知県", "slug": "aichi"},
    {"name": "福岡県", "slug": "fukuoka"},
    {"name": "北海道", "slug": "hokkaido"},
    {"name": "宮城県", "slug": "miyagi"},
    {"name": "広島県", "slug": "hiroshima"},
]

FIELDS = [
    {"name": "IT・プログラミング", "slug": "it",       "icon": "💻"},
    {"name": "AI・機械学習",       "slug": "ai",       "icon": "🤖"},
    {"name": "データ分析",         "slug": "data",     "icon": "📊"},
    {"name": "語学・英会話",       "slug": "english",  "icon": "🌍"},
    {"name": "会計・簿記",         "slug": "bookkeeping","icon": "📒"},
    {"name": "税務・会計",         "slug": "tax",      "icon": "🧾"},
    {"name": "法務・行政",         "slug": "legal",    "icon": "⚖️"},
    {"name": "不動産",             "slug": "estate",   "icon": "🏠"},
    {"name": "医療・介護",         "slug": "medical",  "icon": "🏥"},
    {"name": "キャリア",           "slug": "career",   "icon": "💼"},
    {"name": "経営・ビジネス",     "slug": "business", "icon": "📈"},
]

def base_context():
    return {
        "site_name":      "資格バンク",
        "site_url":       "http://localhost:8000",
        "ga_id":          "",
        "current_year":   date.today().year,
        "nav_categories": NAV_CATEGORIES,
        "nav_areas":      NAV_AREAS,
        "breadcrumbs":    [],
    }

def get_courses(limit=6):
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT c.*, s.name AS school_name
           FROM courses c JOIN schools s ON c.school_id = s.id
           WHERE c.price_after_benefit IS NOT NULL
           ORDER BY c.benefit_rate DESC, c.price_after_benefit ASC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def render_top():
    ctx = base_context()
    ctx.update({
        "page": {
            "title":       "資格バンク｜補助金で最大70%OFF！給付金対象の資格・スキルアップ講座を比較",
            "description": "教育訓練給付金を使えば受講料が最大70%OFF。IT・語学・会計・医療など15,000件以上の対象講座を比較検索。",
        },
        "fields":          FIELDS,
        "areas":           NAV_AREAS,
        "pickup_courses":  get_courses(6),
        "latest_articles": [],  # 記事データは後で追加
    })
    return env.get_template("top.html").render(**ctx)


# ── 簡易HTTPサーバー ──────────────────────
class PreviewHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        print(f"  {self.command} {self.path}")

    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0].rstrip("/") or "/"

        try:
            if path in ("/", "/index.html"):
                html = render_top()
                self._respond(200, html)
            elif path.startswith("/static/"):
                self._serve_static(path)
            else:
                self._respond(404, "<h1>404 Not Found</h1><p>このページはまだ作成されていません。</p>")
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self._respond(500, f"<pre style='color:red'>{tb}</pre>")

    def _respond(self, status, html):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path):
        file_path = ROOT / path.lstrip("/")
        if file_path.exists() and file_path.is_file():
            ext = file_path.suffix.lower()
            mime = {
                ".css": "text/css",
                ".js":  "application/javascript",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".svg": "image/svg+xml",
            }.get(ext, "application/octet-stream")
            data = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)
        else:
            self._respond(404, "Not Found")


if __name__ == "__main__":
    PORT = 8000
    print(f"\n資格バンク プレビューサーバー起動中...")
    print(f"  → http://localhost:{PORT}\n")
    print("  Ctrl+C で停止\n")
    with http.server.HTTPServer(("", PORT), PreviewHandler) as httpd:
        httpd.serve_forever()
