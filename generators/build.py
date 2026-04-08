#!/usr/bin/env python3
"""
資格バンク 静的サイト生成スクリプト

使い方:
    python generators/build.py           # 全ページ生成
    python generators/build.py --clean   # output/ を削除してから生成
    python generators/build.py --top     # トップページのみ再生成

生成されるページ:
    output/index.html                       トップ
    output/search/index.html                検索
    output/category/{slug}/index.html       カテゴリ一覧（7カテゴリ）
    output/course/{id}/index.html           講座詳細（全件）
    output/sitemap.xml                      サイトマップ
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

# Windows環境でのUTF-8出力を強制
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError:
    print("Jinja2が見つかりません。pip install Jinja2 を実行してください。")
    sys.exit(1)

try:
    import markdown as md_lib
except ImportError:
    print("Markdownが見つかりません。pip install Markdown を実行してください。")
    sys.exit(1)

# ── パス定義 ─────────────────────────────────────────────────
ROOT         = Path(__file__).parent.parent
DB_PATH      = ROOT / "data" / "courses.db"
TEMPLATES    = ROOT / "templates"
STATIC       = ROOT / "static"
OUTPUT       = ROOT / "output"
ARTICLES_DIR = ROOT / "articles"

SITE_URL = os.environ.get("SITE_URL", "https://shikaku-bank.com")

# ── カテゴリ定義（slug → DBフィールド名のマッピング）──────────
CATEGORIES = [
    {
        "slug": "design",
        "name": "デザイン",
        "icon": "🎨",
        "fields": [],
        "description": "Webデザイン・グラフィックデザインなどクリエイティブ系の給付金対象講座を比較。",
    },
    {
        "slug": "it",
        "name": "IT・プログラミング",
        "icon": "💻",
        "fields": ["IT", "AI", "データ分析"],
        "description": "プログラミングスクールやAI・データサイエンス講座など、IT分野の給付金対象講座を比較。",
    },
    {
        "slug": "english",
        "name": "語学・英会話",
        "icon": "🌍",
        "fields": ["語学"],
        "description": "英会話・TOEIC対策など語学系の給付金対象講座を比較。",
    },
    {
        "slug": "accounting",
        "name": "会計・簿記",
        "icon": "📊",
        "fields": ["会計", "金融"],
        "description": "簿記・FP・税理士・公認会計士など会計・金融系の給付金対象講座を比較。",
    },
    {
        "slug": "medical",
        "name": "医療・介護",
        "icon": "🏥",
        "fields": ["医療", "介護"],
        "description": "医療事務・介護職員初任者研修など医療・介護系の給付金対象講座を比較。",
    },
    {
        "slug": "estate",
        "name": "不動産・宅建",
        "icon": "🏠",
        "fields": ["不動産"],
        "description": "宅建士・マンション管理士など不動産系の給付金対象講座を比較。",
    },
    {
        "slug": "legal",
        "name": "法務・行政",
        "icon": "⚖️",
        "fields": ["法務", "キャリア"],
        "description": "行政書士・社労士・キャリアコンサルタントなど法務・行政系の給付金対象講座を比較。",
    },
    {
        "slug": "business",
        "name": "経営・ビジネス",
        "icon": "📈",
        "fields": ["経営"],
        "description": "中小企業診断士など経営・ビジネス系の給付金対象講座を比較。",
    },
]

# カテゴリの slug 逆引き（DB field → category slug）
FIELD_TO_CATEGORY: dict[str, str] = {}
for _cat in CATEGORIES:
    for _f in _cat["fields"]:
        FIELD_TO_CATEGORY[_f] = _cat["slug"]

# ナビ用定数（base.html に渡す）
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
    {"name": "東京都",   "slug": "tokyo"},
    {"name": "大阪府",   "slug": "osaka"},
    {"name": "神奈川県", "slug": "kanagawa"},
    {"name": "愛知県",   "slug": "aichi"},
    {"name": "福岡県",   "slug": "fukuoka"},
    {"name": "北海道",   "slug": "hokkaido"},
    {"name": "宮城県",   "slug": "miyagi"},
    {"name": "広島県",   "slug": "hiroshima"},
]

# 検索ページ用フィールドリスト（category slug で絞り込む）
SEARCH_FIELDS = [
    {"name": "IT・プログラミング", "icon": "💻", "slug": "it"},         # IT, AI, データ分析
    {"name": "語学・英会話",       "icon": "🌍", "slug": "english"},    # 語学
    {"name": "会計・簿記・金融",   "icon": "📒", "slug": "accounting"}, # 会計, 金融
    {"name": "法務・行政",         "icon": "⚖️", "slug": "legal"},      # 法務, キャリア
    {"name": "不動産",             "icon": "🏠", "slug": "estate"},     # 不動産
    {"name": "医療・介護",         "icon": "🏥", "slug": "medical"},    # 医療, 介護
    {"name": "経営・ビジネス",     "icon": "📈", "slug": "business"},   # 経営
]

# top.html 用 FIELDS（preview.py と同じ）
TOP_FIELDS = [
    {"name": "IT・プログラミング", "slug": "it",          "icon": "💻"},
    {"name": "AI・機械学習",       "slug": "ai",          "icon": "🤖"},
    {"name": "データ分析",         "slug": "data",        "icon": "📊"},
    {"name": "語学・英会話",       "slug": "english",     "icon": "🌍"},
    {"name": "会計・簿記",         "slug": "bookkeeping", "icon": "📒"},
    {"name": "税務・会計",         "slug": "tax",         "icon": "🧾"},
    {"name": "法務・行政",         "slug": "legal",       "icon": "⚖️"},
    {"name": "不動産",             "slug": "estate",      "icon": "🏠"},
    {"name": "医療・介護",         "slug": "medical",     "icon": "🏥"},
    {"name": "キャリア",           "slug": "career",      "icon": "💼"},
    {"name": "経営・ビジネス",     "slug": "business",    "icon": "📈"},
]


# ── Jinja2 環境 ───────────────────────────────────────────────
def setup_jinja() -> Environment:
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
            dt = datetime.fromisoformat(str(value))
            return dt.strftime(fmt)
        except Exception:
            return str(value)

    env.filters["number_format"] = number_format
    env.filters["dateformat"]    = dateformat
    return env


# ── DB アクセス ───────────────────────────────────────────────
def get_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        print(f"[ERROR] DBが見つかりません: {DB_PATH}")
        print("  先に python data/fetch_courses.py を実行してください。")
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_courses(conn: sqlite3.Connection, fields: list[str] | None = None) -> list[dict]:
    """講座一覧を取得。fields が指定された場合はそのフィールドのみ。"""
    if fields:
        placeholders = ", ".join("?" * len(fields))
        sql = f"""
            SELECT c.*, s.name AS school_name,
                   s.url AS school_url, s.affiliate_url AS school_affiliate_url,
                   s.category AS school_category
            FROM courses c JOIN schools s ON c.school_id = s.id
            WHERE c.field IN ({placeholders}) AND c.is_active = 1
            ORDER BY c.benefit_rate DESC, c.price_after_benefit ASC
        """
        rows = conn.execute(sql, fields).fetchall()
    else:
        sql = """
            SELECT c.*, s.name AS school_name,
                   s.url AS school_url, s.affiliate_url AS school_affiliate_url,
                   s.category AS school_category
            FROM courses c JOIN schools s ON c.school_id = s.id
            WHERE c.is_active = 1
            ORDER BY c.benefit_rate DESC, c.price_after_benefit ASC
        """
        rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def fetch_course(conn: sqlite3.Connection, course_id: int) -> dict | None:
    row = conn.execute(
        """SELECT c.*, s.name AS school_name, s.url AS school_url,
                  s.affiliate_url AS school_affiliate_url,
                  s.description AS school_description,
                  s.category AS school_category
           FROM courses c JOIN schools s ON c.school_id = s.id
           WHERE c.id = ?""",
        (course_id,),
    ).fetchone()
    return dict(row) if row else None


def fetch_school(conn: sqlite3.Connection, school_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM schools WHERE id = ?", (school_id,)).fetchone()
    return dict(row) if row else None


# ── 共通コンテキスト ──────────────────────────────────────────
def base_ctx() -> dict:
    return {
        "site_name":      "資格バンク",
        "site_url":       SITE_URL,
        "ga_id":          "",
        "current_year":   date.today().year,
        "nav_categories": NAV_CATEGORIES,
        "nav_areas":      NAV_AREAS,
        "breadcrumbs":    [],
    }


# ── ファイル書き出し ──────────────────────────────────────────
def write_page(rel_path: str, html: str) -> None:
    """output/ 以下にHTMLを書き出す。rel_path は output/ からの相対パス。"""
    full = OUTPUT / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(html, encoding="utf-8")
    print(f"  ✓  /{rel_path}")


# ── 記事読み込み ──────────────────────────────────────────────
def parse_frontmatter(text: str) -> tuple[dict, str]:
    """YAMLフロントマター（---区切り）を解析してメタデータと本文を返す"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not m:
        return {}, text
    meta: dict = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()
    return meta, m.group(2)


def load_articles() -> list[dict]:
    """articles/ 配下の .md ファイルを読み込み、公開日降順で返す"""
    if not ARTICLES_DIR.exists():
        return []
    articles = []
    for md_path in sorted(ARTICLES_DIR.glob("*.md"), reverse=True):
        if md_path.name == ".gitkeep":
            continue
        text = md_path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        if not meta.get("title") or not meta.get("slug"):
            continue
        content_html = md_lib.markdown(
            body,
            extensions=["extra", "toc", "tables"],
        )
        articles.append({
            **meta,
            "keyword_id":   int(meta.get("keyword_id", 0)),
            "content_html": content_html,
            "body":         body,
        })
    # published_at 降順でソート
    articles.sort(key=lambda a: a.get("published_at", ""), reverse=True)
    return articles


# ── トップページ ──────────────────────────────────────────────
def build_top(env: Environment, conn: sqlite3.Connection, articles: list[dict]) -> list[str]:
    all_courses = fetch_courses(conn)
    total_courses = len(all_courses)
    # アフィリエイトURLがある講座を優先し、分野が偏らないよう各分野から1件ずつ選ぶ
    _seen_fields: set[str] = set()
    pickup: list[dict] = []
    for c in all_courses:
        if (c.get("school_affiliate_url") or c.get("school_url")) and c["field"] not in _seen_fields:
            pickup.append(c)
            _seen_fields.add(c["field"])
            if len(pickup) >= 6:
                break

    # カテゴリ別の実件数を集計
    cat_count: dict[str, int] = {cat["slug"]: 0 for cat in CATEGORIES}
    for c in all_courses:
        slug = FIELD_TO_CATEGORY.get(c["field"], "")
        if slug in cat_count:
            cat_count[slug] += 1

    popular_cats = [
        {
            "icon":  "💻", "name": "IT・プログラミング", "slug": "it",
            "count": cat_count.get("it", 0),
            "color": "bg-blue-50 hover:bg-blue-100 border-blue-100",
        },
        {
            "icon":  "🌍", "name": "語学・英会話", "slug": "english",
            "count": cat_count.get("english", 0),
            "color": "bg-green-50 hover:bg-green-100 border-green-100",
        },
        {
            "icon":  "📊", "name": "会計・簿記", "slug": "accounting",
            "count": cat_count.get("accounting", 0),
            "color": "bg-yellow-50 hover:bg-yellow-100 border-yellow-100",
        },
        {
            "icon":  "🏥", "name": "医療・介護", "slug": "medical",
            "count": cat_count.get("medical", 0),
            "color": "bg-red-50 hover:bg-red-100 border-red-100",
        },
        {
            "icon":  "🏠", "name": "不動産・宅建", "slug": "estate",
            "count": cat_count.get("estate", 0),
            "color": "bg-orange-50 hover:bg-orange-100 border-orange-100",
        },
        {
            "icon":  "🎨", "name": "デザイン・クリエイティブ", "slug": "design",
            "count": cat_count.get("design", 0),
            "color": "bg-purple-50 hover:bg-purple-100 border-purple-100",
        },
    ]

    ctx = base_ctx()
    ctx.update({
        "page": {
            "title":       "資格バンク｜給付金で最大70%OFF！教育訓練給付金対象の資格・スキルアップ講座を比較",
            "description": f"教育訓練給付金を使えば受講料が最大70%OFF。IT・語学・会計・医療など給付金対象講座を比較検索。あなたにぴったりの講座が見つかります。",
            "canonical":   "/",
        },
        "fields":          TOP_FIELDS,
        "areas":           NAV_AREAS,
        "pickup_courses":  pickup,
        "latest_articles": articles[:6],
        "total_courses":   total_courses,
        "popular_cats":    popular_cats,
    })
    html = env.get_template("top.html").render(**ctx)
    write_page("index.html", html)
    return ["/"]


# ── 記事ページ ────────────────────────────────────────────────
def build_article_pages(env: Environment, articles: list[dict]) -> list[str]:
    pages = []

    # 記事一覧
    ctx = base_ctx()
    ctx.update({
        "page": {
            "title":       "コラム一覧｜教育訓練給付金・資格取得ガイド｜資格バンク",
            "description": "教育訓練給付金の使い方・おすすめ資格スクール比較など役立つコラムを掲載。",
            "canonical":   "/articles/",
        },
        "articles": articles,
        "breadcrumbs": [
            {"name": "トップ",    "url": "/"},
            {"name": "コラム一覧", "url": "/articles/"},
        ],
    })
    html = env.get_template("articles.html").render(**ctx)
    write_page("articles/index.html", html)
    pages.append("/articles/")

    # 記事詳細
    for article in articles:
        slug = article["slug"]
        related = [a for a in articles if a["category"] == article["category"] and a["slug"] != slug][:4]
        ctx = base_ctx()
        ctx.update({
            "page": {
                "title":       f"{article['title']}｜資格バンク",
                "description": article.get("excerpt", ""),
                "canonical":   f"/articles/{slug}/",
            },
            "article":          article,
            "related_articles": related,
            "breadcrumbs": [
                {"name": "トップ",    "url": "/"},
                {"name": "コラム一覧", "url": "/articles/"},
                {"name": article["title"], "url": f"/articles/{slug}/"},
            ],
        })
        html = env.get_template("article.html").render(**ctx)
        write_page(f"articles/{slug}/index.html", html)
        pages.append(f"/articles/{slug}/")

    return pages


# ── カテゴリページ ────────────────────────────────────────────
def build_categories(env: Environment, conn: sqlite3.Connection) -> list[str]:
    pages = []
    for cat in CATEGORIES:
        courses = fetch_courses(conn, fields=cat["fields"])
        ctx = base_ctx()
        ctx.update({
            "page": {
                "title":       f"{cat['name']}の給付金対象講座一覧｜資格バンク",
                "description": cat["description"] + "教育訓練給付金で最大70%OFFになる講座を比較。",
                "canonical":   f"/category/{cat['slug']}/",
            },
            "category": cat,
            "courses":  courses,
            "breadcrumbs": [
                {"name": "トップ",    "url": "/"},
                {"name": "カテゴリ一覧", "url": "/category/"},
                {"name": cat["name"], "url": f"/category/{cat['slug']}/"},
            ],
        })
        html = env.get_template("category.html").render(**ctx)
        write_page(f"category/{cat['slug']}/index.html", html)
        pages.append(f"/category/{cat['slug']}/")
    return pages


# ── 講座詳細ページ ────────────────────────────────────────────
def build_courses(env: Environment, conn: sqlite3.Connection) -> list[str]:
    all_courses = fetch_courses(conn)
    pages = []

    # アフィリエイト収益が取れる商業スクール講座を分野別にインデックス化
    # (school_url または school_affiliate_url が存在するもの)
    commercial_by_field: dict[str, list[dict]] = {}
    for c in all_courses:
        if c.get("school_url") or c.get("school_affiliate_url"):
            field = c["field"]
            commercial_by_field.setdefault(field, []).append(c)

    for course in all_courses:
        school = fetch_school(conn, course["school_id"])
        # 同フィールドの関連講座（自分を除く、最大4件）
        related = [
            c for c in all_courses
            if c["field"] == course["field"] and c["id"] != course["id"]
        ][:4]

        # 同分野の商業スクール講座（現スクールを除く、最大4件）
        # URL無しページの収益化に使う
        commercial = [
            c for c in commercial_by_field.get(course["field"], [])
            if c["school_id"] != course["school_id"] and c["id"] != course["id"]
        ][:4]

        # カテゴリslugを特定してパンくず構築
        cat_slug = FIELD_TO_CATEGORY.get(course["field"], "")
        cat_name = next((c["name"] for c in CATEGORIES if c["slug"] == cat_slug), "講座一覧")

        has_cta_url = bool(school and (school.get("affiliate_url") or school.get("url")))

        ctx = base_ctx()
        ctx.update({
            "page": {
                "title":       f"{course['name']}｜{course['school_name']}【給付金{course['benefit_rate']}%OFF】",
                "description": (
                    f"{course['school_name']}「{course['name']}」の詳細。"
                    f"受講料¥{course['price']:,}が教育訓練給付金で"
                    f"実質¥{course['price_after_benefit']:,}〜。"
                    if course.get("price") and course.get("price_after_benefit") else
                    f"{course['school_name']}「{course['name']}」の詳細情報。"
                ),
                "canonical": f"/course/{course['id']}/",
            },
            "course":             course,
            "school":             school,
            "related_courses":    related,
            "commercial_courses": commercial,
            "has_cta_url":        has_cta_url,
            "breadcrumbs": [
                {"name": "トップ",  "url": "/"},
                {"name": cat_name,  "url": f"/category/{cat_slug}/"},
                {"name": course["name"], "url": f"/course/{course['id']}/"},
            ],
        })
        html = env.get_template("course.html").render(**ctx)
        write_page(f"course/{course['id']}/index.html", html)
        pages.append(f"/course/{course['id']}/")

    return pages


# ── 検索ページ ────────────────────────────────────────────────
def build_search(env: Environment, conn: sqlite3.Connection) -> list[str]:
    all_courses = fetch_courses(conn)

    # JS埋め込み用にシリアライズ（必要なフィールドのみ）
    courses_for_js = [
        {
            "id":                  c["id"],
            "name":                c["name"],
            "school_name":         c["school_name"],
            "field":               c["field"],
            "category_slug":       FIELD_TO_CATEGORY.get(c["field"], ""),
            "benefit_type":        c["benefit_type"],
            "benefit_rate":        c["benefit_rate"],
            "price":               c["price"],
            "price_after_benefit": c["price_after_benefit"],
            "duration":            c["duration"],
            "format":              c["format"],
            "prefecture":          c["prefecture"],
            "target_qualification": c["target_qualification"],
            "notes":               c["notes"],
        }
        for c in all_courses
    ]

    ctx = base_ctx()
    ctx.update({
        "page": {
            "title":       "給付金対象講座を検索｜資格バンク",
            "description": "教育訓練給付金の対象講座を分野・エリア・種別で絞り込み検索。IT・語学・会計・医療など全カテゴリを比較できます。",
            "canonical":   "/search/",
        },
        "fields":        SEARCH_FIELDS,
        "total_courses": len(all_courses),
        "courses_json":  json.dumps(courses_for_js, ensure_ascii=False),
        "breadcrumbs": [
            {"name": "トップ", "url": "/"},
            {"name": "講座検索", "url": "/search/"},
        ],
    })
    html = env.get_template("search.html").render(**ctx)
    write_page("search/index.html", html)
    return ["/search/"]


# ── エリア定義 ───────────────────────────────────────────────
AREAS = [
    {"slug": "online",   "name": "オンライン", "icon": "🖥️", "pref": "オンライン"},
    {"slug": "tokyo",    "name": "東京都",     "icon": "🗼", "pref": "東京都"},
    {"slug": "osaka",    "name": "大阪府",     "icon": "🏯", "pref": "大阪府"},
    {"slug": "kanagawa", "name": "神奈川県",   "icon": "⛵", "pref": "神奈川県"},
    {"slug": "aichi",    "name": "愛知県",     "icon": "🌸", "pref": "愛知県"},
    {"slug": "fukuoka",  "name": "福岡県",     "icon": "🍜", "pref": "福岡県"},
    {"slug": "hokkaido", "name": "北海道",     "icon": "🦀", "pref": "北海道"},
    {"slug": "miyagi",   "name": "宮城県",     "icon": "🌊", "pref": "宮城県"},
    {"slug": "hiroshima","name": "広島県",     "icon": "⛩️", "pref": "広島県"},
]


def fetch_courses_by_area(conn: sqlite3.Connection, area: dict) -> list[dict]:
    """エリアに対応する講座を取得（全国 or オンライン or 該当都道府県）"""
    if area["slug"] == "online":
        sql = """
            SELECT c.*, s.name AS school_name
            FROM courses c JOIN schools s ON c.school_id = s.id
            WHERE (c.format LIKE '%オンライン%' OR c.prefecture = '全国')
            AND c.is_active = 1
            ORDER BY c.benefit_rate DESC, c.price_after_benefit ASC
        """
        rows = conn.execute(sql).fetchall()
    else:
        sql = """
            SELECT c.*, s.name AS school_name
            FROM courses c JOIN schools s ON c.school_id = s.id
            WHERE (c.prefecture = '全国' OR c.prefecture LIKE ?)
            AND c.is_active = 1
            ORDER BY c.benefit_rate DESC, c.price_after_benefit ASC
        """
        rows = conn.execute(sql, (f"%{area['pref']}%",)).fetchall()
    return [dict(r) for r in rows]


# ── 補足ページ（固定・エリア・カテゴリ一覧）────────────────────
def build_supplementary_pages(env: Environment, conn: sqlite3.Connection) -> list[str]:
    pages: list[str] = []

    # /about-kyufu/
    ctx = base_ctx()
    ctx.update({
        "page": {
            "title":       "教育訓練給付金とは？3種類の違いと受給条件をわかりやすく解説",
            "description": "教育訓練給付金の仕組みを解説。一般・特定一般・専門実践の違い、受給条件、申請手順まで初めての方向けに紹介します。",
            "canonical":   "/about-kyufu/",
        },
        "breadcrumbs": [{"name": "トップ", "url": "/"}, {"name": "給付金とは", "url": "/about-kyufu/"}],
    })
    write_page("about-kyufu/index.html", env.get_template("about_kyufu.html").render(**ctx))
    pages.append("/about-kyufu/")

    # /category/ 一覧
    cat_counts = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT field, COUNT(*) FROM courses WHERE is_active=1 GROUP BY field"
        )
    }
    cat_items = []
    for cat in CATEGORIES:
        count = sum(cat_counts.get(f, 0) for f in cat["fields"])
        cat_items.append({
            "name": cat["name"], "icon": cat["icon"],
            "url": f"/category/{cat['slug']}/", "count": count,
        })
    ctx = base_ctx()
    ctx.update({
        "page": {
            "title":       "カテゴリ一覧｜給付金対象講座",
            "description": "IT・語学・会計・医療など分野別に給付金対象講座を比較できます。",
            "canonical":   "/category/",
        },
        "items": cat_items,
        "page_ctx": {
            "h1":   "カテゴリから探す",
            "lead": "分野を選んで給付金対象講座を比較してみましょう。",
        },
        "breadcrumbs": [{"name": "トップ", "url": "/"}, {"name": "カテゴリ一覧", "url": "/category/"}],
    })
    # category_list.html に page と page_ctx を統合して渡す
    ctx["page"].update({"h1": "カテゴリから探す", "lead": "分野を選んで給付金対象講座を比較してみましょう。"})
    write_page("category/index.html", env.get_template("category_list.html").render(**ctx))
    pages.append("/category/")

    # /area/ 一覧
    area_items = [
        {"name": a["name"], "icon": a["icon"], "url": f"/area/{a['slug']}/"}
        for a in AREAS
    ]
    ctx = base_ctx()
    ctx.update({
        "page": {
            "title":       "エリアから講座を探す｜資格バンク",
            "description": "都道府県・オンラインでエリアを絞って給付金対象講座を比較できます。",
            "canonical":   "/area/",
            "h1":          "エリアから探す",
            "lead":        "お住まいのエリアや通いやすい地域から講座を探せます。",
        },
        "items": area_items,
        "breadcrumbs": [{"name": "トップ", "url": "/"}, {"name": "エリアから探す", "url": "/area/"}],
    })
    write_page("area/index.html", env.get_template("category_list.html").render(**ctx))
    pages.append("/area/")

    # /area/{slug}/ 各エリアページ（category.html を流用）
    for area in AREAS:
        courses = fetch_courses_by_area(conn, area)
        cat_ctx = {
            "slug":        area["slug"],
            "name":        area["name"],
            "icon":        area["icon"],
            "description": f"{area['name']}で受講できる教育訓練給付金対象の講座を比較。",
        }
        ctx = base_ctx()
        ctx.update({
            "page": {
                "title":       f"{area['name']}の給付金対象講座｜資格バンク",
                "description": cat_ctx["description"],
                "canonical":   f"/area/{area['slug']}/",
            },
            "category": cat_ctx,
            "courses":  courses,
            "breadcrumbs": [
                {"name": "トップ", "url": "/"},
                {"name": "エリアから探す", "url": "/area/"},
                {"name": area["name"], "url": f"/area/{area['slug']}/"},
            ],
        })
        write_page(f"area/{area['slug']}/index.html", env.get_template("category.html").render(**ctx))
        pages.append(f"/area/{area['slug']}/")

    # 固定ページ（about / privacy / disclaimer / contact）
    fixed_pages = [
        {
            "slug": "about",
            "title": "運営者情報",
            "description": "資格バンクの運営者情報です。",
            "h1": "運営者情報",
            "content": """
<h2>サイト名</h2><p>資格バンク</p>
<h2>サイトURL</h2><p>https://shikaku-bank.com</p>
<h2>運営目的</h2>
<p>教育訓練給付金の対象講座を中立な立場で比較・紹介し、
スキルアップを目指す方の講座選びをサポートすることを目的としています。</p>
<h2>収益について</h2>
<p>当サイトは一部のリンクにアフィリエイト広告（成果報酬型広告）を利用しています。</p>
<h2>お問い合わせ</h2><p><a href="/contact/">お問い合わせページ</a>よりご連絡ください。</p>
""",
        },
        {
            "slug": "privacy",
            "title": "プライバシーポリシー",
            "description": "資格バンクのプライバシーポリシーです。",
            "h1": "プライバシーポリシー",
            "content": """
<h2>個人情報の取り扱い</h2>
<p>当サイトでは、お問い合わせの際に氏名・メールアドレス等の個人情報を取得することがあります。
取得した情報はお問い合わせへの返信のみに利用し、第三者に提供することはありません。</p>
<h2>アクセス解析</h2>
<p>当サイトはGoogle Analyticsを使用しています。Cookieを通じてデータを収集しますが、
個人を特定する情報は含まれません。</p>
<h2>アフィリエイト広告</h2>
<p>当サイトはAmazonアソシエイト等のアフィリエイトプログラムに参加しており、
紹介料を受け取ることがあります。</p>
<h2>免責事項</h2>
<p>掲載情報の正確性には万全を期していますが、内容の完全性・正確性を保証するものではありません。
<a href="/disclaimer/">免責事項</a>もご確認ください。</p>
""",
        },
        {
            "slug": "disclaimer",
            "title": "免責事項",
            "description": "資格バンクの免責事項です。",
            "h1": "免責事項",
            "content": """
<h2>情報の正確性について</h2>
<p>当サイトに掲載している受講料・給付金額・講座内容は、各スクール公式サイト等をもとに
独自調査したものです。最新情報は必ず各スクールの公式サイトでご確認ください。</p>
<h2>給付金に関する免責</h2>
<p>教育訓練給付金の受給可否・給付額は、個人の雇用保険加入状況等により異なります。
詳細はお近くのハローワークにお問い合わせください。</p>
<h2>外部リンクについて</h2>
<p>当サイトから外部サイトへのリンクを掲載していますが、リンク先の内容について
当サイトは責任を負いません。</p>
<h2>損害について</h2>
<p>当サイトの情報をご利用されたことによるいかなる損害についても、
当サイトは責任を負いかねます。</p>
""",
        },
        {
            "slug": "contact",
            "title": "お問い合わせ",
            "description": "資格バンクへのお問い合わせはこちら。",
            "h1": "お問い合わせ",
            "content": """
<p>当サイトへのお問い合わせは、以下のメールアドレスまでご連絡ください。</p>
<p>内容を確認の上、順次ご返信いたします。なお、返信まで数日かかる場合があります。</p>
<ul>
  <li>掲載情報の誤りに関するご指摘</li>
  <li>掲載・広告に関するご相談</li>
  <li>その他お問い合わせ</li>
</ul>
<p>※ 教育訓練給付金の受給資格に関するご質問は、お近くのハローワークにお問い合わせください。</p>
""",
        },
    ]
    for fp in fixed_pages:
        ctx = base_ctx()
        ctx.update({
            "page": {
                "title":       fp["title"],
                "description": fp["description"],
                "canonical":   f"/{fp['slug']}/",
                "h1":          fp["h1"],
                "content":     fp["content"],
            },
            "breadcrumbs": [
                {"name": "トップ", "url": "/"},
                {"name": fp["h1"], "url": f"/{fp['slug']}/"},
            ],
        })
        write_page(f"{fp['slug']}/index.html", env.get_template("fixed_page.html").render(**ctx))
        pages.append(f"/{fp['slug']}/")

    return pages


# ── 静的ファイルコピー ────────────────────────────────────────
def copy_static() -> None:
    dst = OUTPUT / "static"
    if dst.exists():
        shutil.rmtree(dst)
    if STATIC.exists():
        shutil.copytree(STATIC, dst)
        print(f"  ✓  /static/ (コピー完了)")
    else:
        dst.mkdir(parents=True, exist_ok=True)
        print(f"  ✓  /static/ (空フォルダ作成)")


# ── sitemap.xml ───────────────────────────────────────────────
def build_sitemap(pages: list[str]) -> None:
    today = date.today().isoformat()
    urls = []
    for path in pages:
        # トップは changefreq: daily、その他は weekly
        freq  = "daily"  if path == "/" else "weekly"
        priority = (
            "1.0" if path == "/" else
            "0.8" if path.startswith("/category/") else
            "0.7" if path.startswith("/articles/") and path != "/articles/" else
            "0.6"
        )
        urls.append(
            f"  <url>\n"
            f"    <loc>{SITE_URL}{path}</loc>\n"
            f"    <lastmod>{today}</lastmod>\n"
            f"    <changefreq>{freq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            f"  </url>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls) +
        "\n</urlset>\n"
    )
    sitemap_path = OUTPUT / "sitemap.xml"
    sitemap_path.write_text(xml, encoding="utf-8")
    print(f"  ✓  /sitemap.xml ({len(pages)} URL)")


# ── _redirects（Cloudflare Pages 用）────────────────────────
def write_redirects() -> None:
    """Cloudflare Pages の SPA フォールバック不要だが、
    よくある旧URL→新URLのリダイレクト例として配置。"""
    content = "# Cloudflare Pages redirects\n# /old-path /new-path 301\n"
    (OUTPUT / "_redirects").write_text(content, encoding="utf-8")
    print("  ✓  /_redirects")


# ── メイン ───────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="資格バンク 静的サイト生成")
    parser.add_argument("--clean", action="store_true", help="output/ を削除してから生成")
    parser.add_argument("--top",   action="store_true", help="トップページのみ再生成")
    args = parser.parse_args()

    if args.clean and OUTPUT.exists():
        shutil.rmtree(OUTPUT)
        print("[clean] output/ を削除しました")

    OUTPUT.mkdir(exist_ok=True)

    env  = setup_jinja()
    conn = get_db()

    try:
        all_pages: list[str] = []
        articles = load_articles()
        print(f"[articles] {len(articles)} 件の記事を読み込みました")

        if args.top:
            print("\n[top] トップページを生成中...")
            all_pages += build_top(env, conn, articles)
        else:
            print("\n[1/6] トップページ")
            all_pages += build_top(env, conn, articles)

            print("\n[2/6] カテゴリページ")
            all_pages += build_categories(env, conn)

            print("\n[3/6] 講座詳細ページ")
            all_pages += build_courses(env, conn)

            print("\n[4/6] 検索ページ")
            all_pages += build_search(env, conn)

            print("\n[5/6] 記事ページ")
            all_pages += build_article_pages(env, articles)

            print("\n[6/7] 補足ページ（給付金とは・エリア・固定ページ等）")
            all_pages += build_supplementary_pages(env, conn)

            print("\n[7/7] 静的ファイル・サイトマップ")
            copy_static()
            build_sitemap(all_pages)
            write_redirects()

        print(f"\n✅ 完了: {len(all_pages)} ページを output/ に生成しました\n")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
