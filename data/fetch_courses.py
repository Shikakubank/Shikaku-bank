"""
教育訓練給付金対象講座データ管理スクリプト

利用規約上、厚労省サイトからの直接スクレイピングは禁止のため、
公式サイトおよび各スクール情報を手動収録した上でDBに投入する。

使い方:
    python data/fetch_courses.py          # DB初期化 + データ投入（全件）
    python data/fetch_courses.py --init   # DBスキーマ作成のみ
    python data/fetch_courses.py --seed   # データ投入のみ（既存データをリセット）
    python data/fetch_courses.py --stats  # 統計表示
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# Windows環境でのUTF-8出力を強制
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = Path(__file__).parent / "courses.db"


# ─────────────────────────────────────────
# スキーマ
# ─────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS schools (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT    NOT NULL,
    url               TEXT,
    affiliate_url     TEXT,
    affiliate_fee_min INTEGER,   -- 最低アフィリエイト報酬（円）
    affiliate_fee_max INTEGER,   -- 最高アフィリエイト報酬（円）
    category          TEXT    NOT NULL,  -- プログラミング/資格/語学/医療介護
    description       TEXT,
    created_at        TEXT    DEFAULT CURRENT_TIMESTAMP,
    updated_at        TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS courses (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    school_id            INTEGER NOT NULL REFERENCES schools(id),
    name                 TEXT    NOT NULL,
    field                TEXT    NOT NULL,  -- IT/AI/データ分析/会計/法務/不動産/医療/介護/語学/キャリア
    benefit_type         TEXT    NOT NULL,  -- 一般/特定一般/専門実践
    benefit_rate         INTEGER NOT NULL,  -- 給付率（%）
    price                INTEGER,           -- 受講料（税込・円）
    price_after_benefit  INTEGER,           -- 給付金適用後の実質負担額（円）
    duration             TEXT,              -- 例: "6ヶ月"
    duration_months      REAL,              -- 数値換算（月）
    format               TEXT,              -- オンライン/通学/通信/通学・オンライン/通信・通学
    prefecture           TEXT,              -- 都道府県 or "全国"
    target_qualification TEXT,              -- 取得目標の資格名
    course_url           TEXT,
    notes                TEXT,              -- 備考（給付条件等）
    is_active            INTEGER DEFAULT 1,
    created_at           TEXT    DEFAULT CURRENT_TIMESTAMP,
    updated_at           TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_courses_field        ON courses(field);
CREATE INDEX IF NOT EXISTS idx_courses_benefit_type ON courses(benefit_type);
CREATE INDEX IF NOT EXISTS idx_courses_school_id    ON courses(school_id);
"""


# ─────────────────────────────────────────
# シードデータ
# ─────────────────────────────────────────
# benefit_rate は 専門実践=70（就職ボーナス込みの最大値）、特定一般=40、一般=20
# price_after_benefit は price × (1 - rate/100) ※給付上限内の場合
# 専門実践の給付上限: 約224万円（3年）、一般は10万円、特定一般は20万円

def calc_after(price: int, rate: int, cap: int) -> int:
    """給付後の実質負担額を計算する。"""
    benefit = min(int(price * rate / 100), cap)
    return price - benefit


SCHOOLS = [
    # id は insert 後に自動付与されるため、ここではリスト順のインデックスで管理
    # (name, url, affiliate_url, fee_min, fee_max, category, description)
    ("テックキャンプ",
     "https://tech-camp.in/",
     "https://tech-camp.in/expert",
     10000, 20000, "プログラミング",
     "転職特化型プログラミングスクール。専門実践教育訓練給付金対象。"),

    ("テックアカデミー",
     "https://techacademy.jp/",
     "https://techacademy.jp/",
     10000, 20000, "プログラミング",
     "オンライン特化。AI・Web・データサイエンス等幅広く対応。"),

    ("DMM WEBCAMP",
     "https://web-camp.io/",
     "https://web-camp.io/",
     10000, 20000, "プログラミング",
     "転職保証付きプログラミングスクール。専門実践教育訓練給付金対象。"),

    ("侍エンジニア",
     "https://www.sejuku.net/",
     "https://www.sejuku.net/",
     10000, 20000, "プログラミング",
     "完全オンライン・マンツーマン指導。専門実践教育訓練給付金対象。"),

    ("Aidemy Premium",
     "https://aidemy.net/",
     "https://aidemy.net/grit/premium/",
     10000, 20000, "プログラミング",
     "AI・機械学習・データサイエンス特化。専門実践教育訓練給付金対象。"),

    ("スタディング",
     "https://studying.jp/",
     "https://studying.jp/",
     3000, 8000, "資格",
     "スマホで学べるオンライン資格スクール。20以上の資格に対応。一般教育訓練給付金対象。"),

    ("フォーサイト",
     "https://www.foresight.jp/",
     "https://www.foresight.jp/",
     3000, 8000, "資格",
     "通信講座特化の資格スクール。合格率業界トップクラス。一般教育訓練給付金対象。"),

    ("ユーキャン",
     "https://www.u-can.co.jp/",
     "https://www.u-can.co.jp/",
     3000, 8000, "資格",
     "国内最大規模の通信教育。29講座が教育訓練給付金対象。"),

    ("LEC東京リーガルマインド",
     "https://www.lec-jp.com/",
     "https://www.lec-jp.com/",
     3000, 8000, "資格",
     "法律・会計・不動産系資格に強い受験指導校。通学・オンライン両対応。"),

    ("TAC",
     "https://www.tac-school.co.jp/",
     "https://www.tac-school.co.jp/",
     3000, 8000, "資格",
     "会計・税務・不動産系資格の老舗受験指導校。全国拠点あり。"),

    ("クレアール",
     "https://www.crear-ac.co.jp/",
     "https://www.crear-ac.co.jp/",
     3000, 8000, "資格",
     "通信講座専門の資格スクール。非常識合格法で効率学習。"),

    ("ニチイ学館",
     "https://www.nichiiko.co.jp/",
     "https://www.nichiiko.co.jp/",
     3000, 5000, "医療介護",
     "医療事務・介護系資格の国内最大手。通学・通信両対応。"),
]


def build_courses(school_ids: dict) -> list:
    """
    school_ids: {school_name: db_id}
    戻り値: courses テーブルに INSERT するレコードのリスト
    各要素: (school_id, name, field, benefit_type, benefit_rate,
             price, price_after_benefit, duration, duration_months,
             format, prefecture, target_qualification, course_url, notes)
    """
    rows = []

    def add(school_name, name, field, btype, brate, price, dur, dur_m,
            fmt, pref, qual, url="", notes=""):
        caps = {20: 100_000, 40: 200_000, 70: 2_240_000}
        pab = calc_after(price, brate, caps[brate]) if price else None
        sid = school_ids[school_name]
        rows.append((sid, name, field, btype, brate, price, pab,
                      dur, dur_m, fmt, pref, qual, url, notes))

    # ── テックキャンプ ──────────────────────
    add("テックキャンプ",
        "エンジニア転職 短期集中スタイル", "IT", "専門実践", 70,
        657_800, "10週間", 2.5, "通学・オンライン", "全国",
        "プログラミングエンジニア",
        "https://tech-camp.in/expert/grant",
        "就職ボーナス込みで最大70%給付（給付上限あり）")

    add("テックキャンプ",
        "エンジニア転職 夜間・休日スタイル", "IT", "専門実践", 70,
        877_800, "6ヶ月", 6.0, "通学・オンライン", "全国",
        "プログラミングエンジニア",
        "https://tech-camp.in/expert/grant",
        "就職ボーナス込みで最大70%給付（給付上限あり）")

    # ── テックアカデミー ────────────────────
    add("テックアカデミー",
        "Webエンジニア転職保証コース", "IT", "専門実践", 70,
        437_800, "16週間", 4.0, "オンライン", "全国",
        "プログラミングエンジニア",
        "https://techacademy.jp/bootcamp/",
        "転職保証付き。給付金適用で実質約13万円〜")

    add("テックアカデミー",
        "AIコース（16週）", "AI", "一般", 20,
        185_900, "16週間", 4.0, "オンライン", "全国",
        "AI・機械学習エンジニア",
        "https://techacademy.jp/school/machine-learning/")

    add("テックアカデミー",
        "データサイエンスコース（16週）", "データ分析", "一般", 20,
        185_900, "16週間", 4.0, "オンライン", "全国",
        "データサイエンティスト",
        "https://techacademy.jp/school/datascience/")

    # ── DMM WEBCAMP ────────────────────────
    add("DMM WEBCAMP",
        "専門技術コース（16週）", "IT", "専門実践", 70,
        910_800, "16週間", 4.0, "オンライン", "全国",
        "プログラミングエンジニア",
        "https://web-camp.io/reskilling/",
        "就職ボーナス込みで最大70%給付")

    add("DMM WEBCAMP",
        "就業両立コース（24週）", "IT", "専門実践", 70,
        910_800, "24週間", 6.0, "オンライン", "全国",
        "プログラミングエンジニア",
        "https://web-camp.io/reskilling/",
        "働きながら受講可能。就職ボーナス込みで最大70%給付")

    # ── 侍エンジニア ───────────────────────
    add("侍エンジニア",
        "Javaコース", "IT", "専門実践", 70,
        594_000, "6ヶ月", 6.0, "オンライン", "全国",
        "Javaエンジニア",
        "https://www.sejuku.net/",
        "入学金99,000円含む。専門実践教育訓練給付金対象")

    add("侍エンジニア",
        "Pythonコース", "IT", "専門実践", 70,
        594_000, "6ヶ月", 6.0, "オンライン", "全国",
        "Pythonエンジニア",
        "https://www.sejuku.net/",
        "入学金99,000円含む。専門実践教育訓練給付金対象")

    # ── Aidemy Premium ─────────────────────
    add("Aidemy Premium",
        "AIアプリ開発講座（3ヶ月）", "AI", "専門実践", 70,
        528_000, "3ヶ月", 3.0, "オンライン", "全国",
        "AIエンジニア",
        "https://aidemy.net/grit/premium/benefit/",
        "専門実践教育訓練給付金対象")

    add("Aidemy Premium",
        "データ分析講座（3ヶ月）", "データ分析", "専門実践", 70,
        528_000, "3ヶ月", 3.0, "オンライン", "全国",
        "データアナリスト",
        "https://aidemy.net/grit/premium/benefit/")

    add("Aidemy Premium",
        "E資格対策講座", "AI", "専門実践", 70,
        327_800, "3ヶ月", 3.0, "オンライン", "全国",
        "JDLA Deep Learning for ENGINEER（E資格）",
        "https://aidemy.net/grit/premium/benefit/")

    # ── スタディング ───────────────────────
    add("スタディング",
        "中小企業診断士講座", "経営", "一般", 20,
        54_780, "8〜12ヶ月", 10.0, "オンライン", "全国",
        "中小企業診断士",
        "https://studying.jp/shindanshi/")

    add("スタディング",
        "宅地建物取引士講座", "不動産", "一般", 20,
        14_960, "4〜6ヶ月", 5.0, "オンライン", "全国",
        "宅地建物取引士（宅建士）",
        "https://studying.jp/takken/")

    add("スタディング",
        "社会保険労務士講座", "法務", "一般", 20,
        49_500, "6〜10ヶ月", 8.0, "オンライン", "全国",
        "社会保険労務士（社労士）",
        "https://studying.jp/sharoushi/")

    add("スタディング",
        "簿記2・3級セットコース", "会計", "一般", 20,
        15_400, "3〜6ヶ月", 4.5, "オンライン", "全国",
        "日商簿記2・3級",
        "https://studying.jp/boki/")

    add("スタディング",
        "FP2・3級セットコース", "金融", "一般", 20,
        14_300, "3〜5ヶ月", 4.0, "オンライン", "全国",
        "ファイナンシャル・プランニング技能士2・3級",
        "https://studying.jp/fp/")

    add("スタディング",
        "行政書士講座", "法務", "一般", 20,
        49_500, "6〜10ヶ月", 8.0, "オンライン", "全国",
        "行政書士",
        "https://studying.jp/gyosei/")

    add("スタディング",
        "司法書士講座", "法務", "一般", 20,
        79_800, "12〜18ヶ月", 15.0, "オンライン", "全国",
        "司法書士",
        "https://studying.jp/shihou/")

    add("スタディング",
        "ITパスポート講座", "IT", "一般", 20,
        4_950, "2〜3ヶ月", 2.5, "オンライン", "全国",
        "ITパスポート試験（iパス）",
        "https://studying.jp/itpassport/")

    add("スタディング",
        "応用情報技術者講座", "IT", "一般", 20,
        14_960, "4〜6ヶ月", 5.0, "オンライン", "全国",
        "応用情報技術者試験",
        "https://studying.jp/joho/")

    # ── フォーサイト ───────────────────────
    add("フォーサイト",
        "宅建士バリューセット3（テキスト+問題集+過去問）", "不動産", "一般", 20,
        52_800, "4〜6ヶ月", 5.0, "通信", "全国",
        "宅地建物取引士（宅建士）",
        "https://www.foresight.jp/takken/")

    add("フォーサイト",
        "社会保険労務士バリューセット2", "法務", "一般", 20,
        78_800, "8〜12ヶ月", 10.0, "通信", "全国",
        "社会保険労務士（社労士）",
        "https://www.foresight.jp/sharoushi/")

    add("フォーサイト",
        "FP2・3級バリューセット", "金融", "一般", 20,
        24_800, "3〜4ヶ月", 3.5, "通信", "全国",
        "ファイナンシャル・プランニング技能士2・3級",
        "https://www.foresight.jp/fp/")

    add("フォーサイト",
        "行政書士バリューセット2", "法務", "一般", 20,
        78_800, "8〜12ヶ月", 10.0, "通信", "全国",
        "行政書士",
        "https://www.foresight.jp/gyosei/")

    add("フォーサイト",
        "マンション管理士・管理業務主任者コース", "不動産", "一般", 20,
        36_800, "4〜6ヶ月", 5.0, "通信", "全国",
        "マンション管理士・管理業務主任者",
        "https://www.foresight.jp/kanri/")

    # ── ユーキャン ─────────────────────────
    add("ユーキャン",
        "宅地建物取引士講座", "不動産", "一般", 20,
        61_000, "7ヶ月", 7.0, "通信", "全国",
        "宅地建物取引士（宅建士）",
        "https://www.u-can.co.jp/course/data/in_html/1261/")

    add("ユーキャン",
        "医療事務講座（医科）", "医療", "一般", 20,
        40_700, "4ヶ月", 4.0, "通信", "全国",
        "医療事務認定実務者・医療事務技能審査試験",
        "https://www.u-can.co.jp/course/data/in_html/51/")

    add("ユーキャン",
        "介護福祉士講座", "介護", "一般", 20,
        59_000, "12ヶ月", 12.0, "通信", "全国",
        "介護福祉士",
        "https://www.u-can.co.jp/course/data/in_html/61/")

    add("ユーキャン",
        "FP技能士2・3級講座", "金融", "一般", 20,
        40_700, "6ヶ月", 6.0, "通信", "全国",
        "ファイナンシャル・プランニング技能士2・3級",
        "https://www.u-can.co.jp/course/data/in_html/81/")

    add("ユーキャン",
        "日商簿記2・3級講座", "会計", "一般", 20,
        40_700, "6ヶ月", 6.0, "通信", "全国",
        "日商簿記2・3級",
        "https://www.u-can.co.jp/course/data/in_html/91/")

    # ── LEC ───────────────────────────────
    add("LEC東京リーガルマインド",
        "宅地建物取引士 合格コース", "不動産", "一般", 20,
        168_000, "6〜10ヶ月", 8.0, "通学・オンライン", "全国",
        "宅地建物取引士（宅建士）",
        "https://www.lec-jp.com/takken/")

    add("LEC東京リーガルマインド",
        "社会保険労務士 合格コース", "法務", "一般", 20,
        242_000, "8〜12ヶ月", 10.0, "通学・オンライン", "全国",
        "社会保険労務士（社労士）",
        "https://www.lec-jp.com/sharoushi/")

    add("LEC東京リーガルマインド",
        "キャリアコンサルタント養成講座", "キャリア", "専門実践", 70,
        297_500, "4〜6ヶ月", 5.0, "通学・オンライン", "全国",
        "国家資格キャリアコンサルタント",
        "https://www.lec-jp.com/cc/",
        "専門実践教育訓練給付金対象")

    add("LEC東京リーガルマインド",
        "行政書士 合格コース", "法務", "一般", 20,
        176_000, "8〜12ヶ月", 10.0, "通学・オンライン", "全国",
        "行政書士",
        "https://www.lec-jp.com/gyosei/")

    # ── TAC ───────────────────────────────
    add("TAC",
        "日商簿記2・3級 本科生", "会計", "一般", 20,
        34_000, "3〜5ヶ月", 4.0, "通学・オンライン", "全国",
        "日商簿記2・3級",
        "https://www.tac-school.co.jp/kouza_boki.html")

    add("TAC",
        "税理士 本科生（簿財2科目）", "会計", "一般", 20,
        307_000, "12〜18ヶ月", 15.0, "通学・オンライン", "全国",
        "税理士",
        "https://www.tac-school.co.jp/kouza_zeirishi.html")

    add("TAC",
        "公認会計士 本科生", "会計", "一般", 20,
        638_000, "18〜24ヶ月", 21.0, "通学・オンライン", "全国",
        "公認会計士",
        "https://www.tac-school.co.jp/kouza_kaikei.html")

    add("TAC",
        "宅地建物取引士 本科生", "不動産", "一般", 20,
        64_000, "6〜10ヶ月", 8.0, "通学・オンライン", "全国",
        "宅地建物取引士（宅建士）",
        "https://www.tac-school.co.jp/kouza_takken.html")

    add("TAC",
        "社会保険労務士 本科生", "法務", "一般", 20,
        195_000, "8〜12ヶ月", 10.0, "通学・オンライン", "全国",
        "社会保険労務士（社労士）",
        "https://www.tac-school.co.jp/kouza_sharoshi.html")

    add("TAC",
        "中小企業診断士 1・2次本科生", "経営", "一般", 20,
        195_000, "12〜18ヶ月", 15.0, "通学・オンライン", "全国",
        "中小企業診断士",
        "https://www.tac-school.co.jp/kouza_chusho.html")

    # ── クレアール ─────────────────────────
    add("クレアール",
        "宅建士 セーフティコース", "不動産", "一般", 20,
        50_600, "4〜8ヶ月", 6.0, "通信", "全国",
        "宅地建物取引士（宅建士）",
        "https://www.crear-ac.co.jp/takken/")

    add("クレアール",
        "社会保険労務士 セーフティコース", "法務", "一般", 20,
        88_000, "6〜12ヶ月", 9.0, "通信", "全国",
        "社会保険労務士（社労士）",
        "https://www.crear-ac.co.jp/sharoshi/")

    add("クレアール",
        "行政書士 セーフティコース", "法務", "一般", 20,
        70_400, "6〜12ヶ月", 9.0, "通信", "全国",
        "行政書士",
        "https://www.crear-ac.co.jp/gyosei/")

    add("クレアール",
        "公認会計士 トータルセーフティコース", "会計", "一般", 20,
        383_800, "18〜36ヶ月", 24.0, "通信", "全国",
        "公認会計士",
        "https://www.crear-ac.co.jp/cpa/")

    add("クレアール",
        "税理士 会計科目セーフティコース", "会計", "一般", 20,
        131_000, "12〜18ヶ月", 15.0, "通信", "全国",
        "税理士（会計2科目）",
        "https://www.crear-ac.co.jp/zeirishi/")

    add("クレアール",
        "中小企業診断士 セーフティコース", "経営", "一般", 20,
        88_000, "8〜14ヶ月", 11.0, "通信", "全国",
        "中小企業診断士",
        "https://www.crear-ac.co.jp/shindanshi/")

    # ── ニチイ学館 ─────────────────────────
    add("ニチイ学館",
        "医療事務講座（医科）", "医療", "一般", 20,
        62_370, "4ヶ月", 4.0, "通学・通信", "全国",
        "医療事務認定実務者・医療事務技能審査試験",
        "https://www.e-nichii.net/lp/iryoujimu/")

    add("ニチイ学館",
        "医療事務講座（歯科）", "医療", "一般", 20,
        45_870, "3ヶ月", 3.0, "通学・通信", "全国",
        "医療事務認定実務者（歯科）",
        "https://www.e-nichii.net/lp/shikaimu/")

    add("ニチイ学館",
        "介護職員初任者研修", "介護", "一般", 20,
        90_420, "1〜3ヶ月", 2.0, "通学", "全国",
        "介護職員初任者研修修了（旧ヘルパー2級）",
        "https://www.nichiiko.co.jp/train/")

    add("ニチイ学館",
        "介護福祉士実務者研修", "介護", "一般", 20,
        118_800, "6ヶ月", 6.0, "通信・通学", "全国",
        "介護福祉士実務者研修修了（介護福祉士受験資格）",
        "https://www.nichiiko.co.jp/train/")

    return rows


# ─────────────────────────────────────────
# DB操作
# ─────────────────────────────────────────

def init_db(conn: sqlite3.Connection):
    conn.executescript(SCHEMA)
    conn.commit()
    print("[init] スキーマ作成完了")


def seed_db(conn: sqlite3.Connection):
    # 既存データをリセット
    conn.execute("DELETE FROM courses")
    conn.execute("DELETE FROM schools")
    conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('courses','schools')")
    conn.commit()

    # schools INSERT
    conn.executemany(
        """INSERT INTO schools
               (name, url, affiliate_url, affiliate_fee_min, affiliate_fee_max,
                category, description)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [(s[0], s[1], s[2], s[3], s[4], s[5], s[6]) for s in SCHOOLS],
    )
    conn.commit()

    # school_ids マップを取得
    rows = conn.execute("SELECT id, name FROM schools").fetchall()
    school_ids = {name: sid for sid, name in rows}

    # courses INSERT
    course_rows = build_courses(school_ids)
    conn.executemany(
        """INSERT INTO courses
               (school_id, name, field, benefit_type, benefit_rate,
                price, price_after_benefit, duration, duration_months,
                format, prefecture, target_qualification, course_url, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        course_rows,
    )
    conn.commit()

    n_schools = conn.execute("SELECT COUNT(*) FROM schools").fetchone()[0]
    n_courses = conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
    print(f"[seed] スクール {n_schools} 件、講座 {n_courses} 件を投入しました")


def print_stats(conn: sqlite3.Connection):
    print("\n─── 統計 ───────────────────────────────────")
    total = conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
    print(f"総講座数: {total} 件")

    print("\n■ 給付金種別:")
    for row in conn.execute(
        "SELECT benefit_type, COUNT(*) FROM courses GROUP BY benefit_type ORDER BY COUNT(*) DESC"
    ):
        print(f"  {row[0]}: {row[1]} 件")

    print("\n■ 分野別:")
    for row in conn.execute(
        "SELECT field, COUNT(*) FROM courses GROUP BY field ORDER BY COUNT(*) DESC"
    ):
        print(f"  {row[0]}: {row[1]} 件")

    print("\n■ スクール別 講座数:")
    for row in conn.execute(
        """SELECT s.name, COUNT(c.id)
           FROM schools s JOIN courses c ON s.id = c.school_id
           GROUP BY s.id ORDER BY COUNT(c.id) DESC"""
    ):
        print(f"  {row[0]}: {row[1]} 件")

    print("\n■ 実質負担額ランキング（安い順 TOP10）:")
    for row in conn.execute(
        """SELECT s.name, c.name, c.price, c.price_after_benefit, c.benefit_rate
           FROM courses c JOIN schools s ON c.school_id = s.id
           WHERE c.price_after_benefit IS NOT NULL
           ORDER BY c.price_after_benefit ASC LIMIT 10"""
    ):
        print(f"  {row[0]} / {row[1]}")
        print(f"    受講料: ¥{row[2]:,} → 実質 ¥{row[3]:,}（給付率{row[4]}%）")
    print("─────────────────────────────────────────\n")


# ─────────────────────────────────────────
# エントリポイント
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="教育訓練給付金 講座DB管理")
    parser.add_argument("--init",  action="store_true", help="スキーマ作成のみ")
    parser.add_argument("--seed",  action="store_true", help="データ投入のみ")
    parser.add_argument("--stats", action="store_true", help="統計表示")
    args = parser.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)

    try:
        if args.init:
            init_db(conn)
        elif args.seed:
            seed_db(conn)
        elif args.stats:
            print_stats(conn)
        else:
            # デフォルト: 初期化 + データ投入 + 統計
            init_db(conn)
            seed_db(conn)
            print_stats(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
