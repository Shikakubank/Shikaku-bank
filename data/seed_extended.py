"""
拡張データ投入スクリプト v2
方式1: 厚労省プレスリリースPDFデータ（専門実践・特定一般 令和8年4月1日付）
方式2: 主要スクール手動データ（15+校、約120講座）
方式3: 資格マスターテーブル（50資格）
方式4: 自動車教習所（大型免許・二種免許）
方式5: 看護・介護専門学校（PDFより取込）
方式6: MBA・大学院
方式7: ハロートレーニング（別テーブル）
方式8: 自治体独自給付金（別テーブル）

使い方:
    python data/seed_extended.py
"""

import sys, sqlite3, json, re
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = Path(__file__).parent / "courses.db"
JSON_PATH = Path(__file__).parent / "mhlw_pdf_courses.json"


# ─────────────────────────────────────────
# スキーマ拡張
# ─────────────────────────────────────────
MIGRATIONS = [
    "ALTER TABLE courses ADD COLUMN source      TEXT DEFAULT 'スクール公式サイト'",
    "ALTER TABLE courses ADD COLUMN source_url  TEXT",
    "ALTER TABLE courses ADD COLUMN course_number TEXT",
    "ALTER TABLE schools ADD COLUMN source      TEXT DEFAULT 'スクール公式サイト'",
    """CREATE TABLE IF NOT EXISTS qualifications (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL UNIQUE,
        name_kana       TEXT,
        field           TEXT NOT NULL,
        category_slug   TEXT NOT NULL,
        qual_type       TEXT,
        difficulty      INTEGER,
        pass_rate       REAL,
        exam_fee        INTEGER,
        exam_schedule   TEXT,
        official_url    TEXT,
        description     TEXT,
        created_at      TEXT DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS local_benefits (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        prefecture  TEXT NOT NULL,
        name        TEXT NOT NULL,
        description TEXT,
        max_amount  INTEGER,
        target      TEXT,
        fields      TEXT,
        url         TEXT,
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS hello_training (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        name         TEXT NOT NULL,
        field        TEXT,
        target_type  TEXT,
        duration     TEXT,
        cost         TEXT,
        description  TEXT,
        prefecture   TEXT,
        url          TEXT,
        created_at   TEXT DEFAULT CURRENT_TIMESTAMP
    )""",
]


# ─────────────────────────────────────────
# 手動スクールデータ（方式2・4・6）
# ─────────────────────────────────────────
MANUAL_SCHOOLS = [
    {"name": "デジタルハリウッドSTUDIO",   "url": "https://school.dhw.co.jp/", "category": "IT",    "source": "スクール公式サイト",
     "description": "WebデザイナーやAIクリエイター育成のクリエイティブ系スクール"},
    {"name": "Winスクール",                "url": "https://www.winschool.jp/",  "category": "IT",    "source": "スクール公式サイト",
     "description": "CAD・Webデザイン・プログラミングの実務スキルを習得できるスクール"},
    {"name": "KENスクール",                "url": "https://www.ken-school.com/","category": "IT",    "source": "スクール公式サイト",
     "description": "Web・DTP・動画編集など制作系スキルを習得できるスクール"},
    {"name": "RUNTEQ",                     "url": "https://runteq.jp/",         "category": "IT",    "source": "スクール公式サイト",
     "description": "Webエンジニア転職特化型プログラミングスクール。専門実践教育訓練給付金対象"},
    {"name": "ポテパンキャンプ",           "url": "https://potepan.com/",       "category": "IT",    "source": "スクール公式サイト",
     "description": "Ruby on Rails特化型のプログラミングスクール"},
    {"name": "キカガク",                   "url": "https://www.kikagaku.co.jp/","category": "IT",    "source": "スクール公式サイト",
     "description": "AI・データサイエンス専門スクール。専門実践教育訓練給付金対象"},
    {"name": "アビバ",                     "url": "https://www.aviva.co.jp/",   "category": "IT",    "source": "スクール公式サイト",
     "description": "ExcelやWordなどOfficeスキルとIT資格を習得できるスクール"},
    {"name": "東京デザインテクノロジーセンター", "url": "https://www.tech.ac.jp/", "category": "IT", "source": "スクール公式サイト",
     "description": "映像・CG・ゲームなどクリエイティブ専門学校"},
    {"name": "資格の大原",                 "url": "https://www.o-hara.ac.jp/",  "category": "資格",  "source": "スクール公式サイト",
     "description": "簿記・税理士・公認会計士・社労士など会計・法務系に強い資格スクール"},
    {"name": "大栄",                       "url": "https://www.daiei-edu.co.jp/","category": "資格", "source": "スクール公式サイト",
     "description": "宅建・簿記・FP・行政書士など多数の資格対策講座を開講するスクール"},
    {"name": "東京CPA会計学院",            "url": "https://cpa-net.jp/",         "category": "資格", "source": "スクール公式サイト",
     "description": "公認会計士・税理士試験対策に特化した専門スクール"},
    {"name": "ECC外語学院",                "url": "https://www.ecc.co.jp/",      "category": "語学", "source": "スクール公式サイト",
     "description": "英会話・英検・TOEICなど語学系スクール"},
    {"name": "ベルリッツ",                 "url": "https://www.berlitz.com/ja-jp/","category": "語学","source": "スクール公式サイト",
     "description": "ビジネス英語・英会話の世界的語学スクール"},
    {"name": "NOVA",                       "url": "https://www.nova.co.jp/",     "category": "語学", "source": "スクール公式サイト",
     "description": "全国展開の英会話スクール。教育訓練給付金対象コースあり"},
    {"name": "TBC英語スクール",            "url": "https://tbc-english.com/",    "category": "語学", "source": "スクール公式サイト",
     "description": "TOEIC特化型英語スクール"},
    {"name": "三幸福祉カレッジ",           "url": "https://www.sanko-fukushi.com/","category": "医療介護","source": "スクール公式サイト",
     "description": "介護・医療系資格取得に特化したスクール。全国展開"},
    {"name": "日本医療事務協会",           "url": "https://www.ijinet.com/",     "category": "医療介護","source": "スクール公式サイト",
     "description": "医療事務資格取得の専門スクール"},
    {"name": "ソラスト",                   "url": "https://www.solasto.co.jp/education/","category": "医療介護","source": "スクール公式サイト",
     "description": "医療事務・調剤薬局事務・介護系の教育スクール"},
    {"name": "ヒューマンアカデミー",       "url": "https://haa.athuman.com/",    "category": "資格", "source": "スクール公式サイト",
     "description": "キャリアコンサルタント・日本語教師・保育士など多分野の資格スクール"},
    {"name": "日本マンパワー",             "url": "https://www.nipponmanpower.co.jp/","category": "資格","source": "スクール公式サイト",
     "description": "キャリアコンサルタント養成講座を主力とする人材育成機関"},
    {"name": "コヤマドライビングスクール", "url": "https://www.koyama.co.jp/",   "category": "その他","source": "スクール公式サイト",
     "description": "首都圏展開の自動車教習所。大型・二種免許の教育訓練給付金対象コースあり"},
    {"name": "KDS関東自動車学校",          "url": "https://www.kds-school.co.jp/","category": "その他","source": "スクール公式サイト",
     "description": "神奈川県の自動車教習所。大型・二種免許コースが給付金対象"},
    {"name": "グロービス経営大学院",       "url": "https://mba.globis.ac.jp/",   "category": "経営", "source": "スクール公式サイト",
     "description": "日本最大のビジネス・スクール。MBAが専門実践教育訓練給付金対象"},
    {"name": "早稲田大学ビジネス・スクール","url": "https://www.waseda.jp/fcom/wbs/","category": "経営","source": "スクール公式サイト",
     "description": "早稲田大学の大学院経営管理研究科。MBAが専門実践教育訓練給付金対象"},
    {"name": "BBT大学院大学",              "url": "https://www.bbt757.com/",      "category": "経営","source": "スクール公式サイト",
     "description": "ビジネス・ブレークスルー大学院。完全オンラインMBAが専門実践教育訓練給付金対象"},
]

MANUAL_COURSES = [
    # ── デジタルハリウッドSTUDIO ──
    {"school": "デジタルハリウッドSTUDIO", "name": "Webデザイナー専攻",           "field": "IT",    "benefit_type": "一般",    "benefit_rate": 20, "price": 548000, "duration": "6か月",  "format": "オンライン", "target_qualification": "Webクリエイター能力認定試験"},
    {"school": "デジタルハリウッドSTUDIO", "name": "Webプロデューサー専攻",        "field": "IT",    "benefit_type": "一般",    "benefit_rate": 20, "price": 458000, "duration": "6か月",  "format": "オンライン", "target_qualification": None},
    {"school": "デジタルハリウッドSTUDIO", "name": "AIクリエイター専攻",           "field": "AI",    "benefit_type": "一般",    "benefit_rate": 20, "price": 548000, "duration": "6か月",  "format": "オンライン", "target_qualification": "Python 3 エンジニア認定基礎試験"},
    {"school": "デジタルハリウッドSTUDIO", "name": "動画クリエイター専攻",         "field": "IT",    "benefit_type": "一般",    "benefit_rate": 20, "price": 438000, "duration": "6か月",  "format": "オンライン", "target_qualification": None},
    {"school": "デジタルハリウッドSTUDIO", "name": "グラフィックデザイナー専攻",   "field": "IT",    "benefit_type": "一般",    "benefit_rate": 20, "price": 498000, "duration": "6か月",  "format": "通学",       "target_qualification": None},
    # ── Winスクール ──
    {"school": "Winスクール", "name": "CADオペレーター養成コース",       "field": "IT",  "benefit_type": "一般", "benefit_rate": 20, "price": 165000, "duration": "6か月",  "format": "通学・オンライン", "target_qualification": "CAD利用技術者試験"},
    {"school": "Winスクール", "name": "Javaプログラマー養成コース",      "field": "IT",  "benefit_type": "一般", "benefit_rate": 20, "price": 198000, "duration": "6か月",  "format": "通学",           "target_qualification": "Oracle認定Javaプログラマ"},
    {"school": "Winスクール", "name": "Webデザイナー養成コース",         "field": "IT",  "benefit_type": "一般", "benefit_rate": 20, "price": 143000, "duration": "6か月",  "format": "通学",           "target_qualification": "ウェブデザイン技能検定"},
    {"school": "Winスクール", "name": "Pythonプログラミング基礎コース",   "field": "AI",  "benefit_type": "一般", "benefit_rate": 20, "price": 154000, "duration": "4か月",  "format": "通学・オンライン", "target_qualification": "Python 3 エンジニア認定基礎試験"},
    {"school": "Winスクール", "name": "ネットワーク管理者養成コース",    "field": "IT",  "benefit_type": "一般", "benefit_rate": 20, "price": 198000, "duration": "6か月",  "format": "通学",           "target_qualification": "CCNA"},
    {"school": "Winスクール", "name": "AIコース（機械学習・ディープラーニング）","field": "AI","benefit_type": "一般","benefit_rate": 20,"price": 220000,"duration": "6か月","format": "通学・オンライン","target_qualification": "G検定"},
    # ── KENスクール ──
    {"school": "KENスクール", "name": "Webデザイナーコース",         "field": "IT",  "benefit_type": "一般", "benefit_rate": 20, "price": 220000, "duration": "6か月",  "format": "通学", "target_qualification": "Webクリエイター能力認定試験"},
    {"school": "KENスクール", "name": "プログラマーコース",          "field": "IT",  "benefit_type": "一般", "benefit_rate": 20, "price": 280000, "duration": "6か月",  "format": "通学", "target_qualification": None},
    {"school": "KENスクール", "name": "DTPオペレーターコース",       "field": "IT",  "benefit_type": "一般", "benefit_rate": 20, "price": 176000, "duration": "6か月",  "format": "通学", "target_qualification": None},
    {"school": "KENスクール", "name": "動画・映像制作コース",        "field": "IT",  "benefit_type": "一般", "benefit_rate": 20, "price": 198000, "duration": "6か月",  "format": "通学", "target_qualification": None},
    # ── RUNTEQ ──
    {"school": "RUNTEQ", "name": "Webエンジニア育成コース（フルタイム）", "field": "IT", "benefit_type": "専門実践", "benefit_rate": 70, "price": 550000, "duration": "9か月",  "format": "オンライン", "target_qualification": None},
    {"school": "RUNTEQ", "name": "Webエンジニア育成コース（パート）",   "field": "IT", "benefit_type": "専門実践", "benefit_rate": 70, "price": 550000, "duration": "12か月", "format": "オンライン", "target_qualification": None},
    # ── ポテパンキャンプ ──
    {"school": "ポテパンキャンプ", "name": "Railsエンジニアコース",   "field": "IT", "benefit_type": "一般", "benefit_rate": 20, "price": 440000, "duration": "6か月",  "format": "オンライン", "target_qualification": None},
    # ── キカガク ──
    {"school": "キカガク", "name": "AI・データサイエンスコース（専門実践）", "field": "AI",  "benefit_type": "専門実践", "benefit_rate": 70, "price": 836000, "duration": "12か月", "format": "オンライン", "target_qualification": "E資格"},
    {"school": "キカガク", "name": "Pythonエンジニア育成コース",              "field": "AI",  "benefit_type": "一般",    "benefit_rate": 20, "price": 165000, "duration": "3か月",  "format": "オンライン", "target_qualification": "Python 3 エンジニア認定基礎試験"},
    {"school": "キカガク", "name": "機械学習エンジニアコース",                "field": "AI",  "benefit_type": "一般",    "benefit_rate": 20, "price": 264000, "duration": "6か月",  "format": "オンライン", "target_qualification": "G検定"},
    {"school": "キカガク", "name": "データサイエンティスト養成コース",        "field": "データ分析", "benefit_type": "一般", "benefit_rate": 20, "price": 330000, "duration": "6か月","format": "オンライン", "target_qualification": "統計検定2級"},
    # ── アビバ ──
    {"school": "アビバ", "name": "Excel・Wordマスターコース",   "field": "IT", "benefit_type": "一般", "benefit_rate": 20, "price": 88000,  "duration": "3か月",  "format": "通学", "target_qualification": "MOS（Word/Excel）"},
    {"school": "アビバ", "name": "ITパスポート合格コース",       "field": "IT", "benefit_type": "一般", "benefit_rate": 20, "price": 77000,  "duration": "3か月",  "format": "通学・オンライン", "target_qualification": "ITパスポート"},
    {"school": "アビバ", "name": "基本情報技術者試験対策コース", "field": "IT", "benefit_type": "一般", "benefit_rate": 20, "price": 110000, "duration": "6か月",  "format": "通学", "target_qualification": "基本情報技術者"},
    # ── 東京デザインテクノロジーセンター ──
    {"school": "東京デザインテクノロジーセンター", "name": "映像・CGクリエイターコース",  "field": "IT", "benefit_type": "専門実践", "benefit_rate": 70, "price": 770000, "duration": "12か月", "format": "通学", "target_qualification": None, "prefecture": "東京都"},
    {"school": "東京デザインテクノロジーセンター", "name": "ゲームクリエイターコース",     "field": "IT", "benefit_type": "専門実践", "benefit_rate": 70, "price": 770000, "duration": "12か月", "format": "通学", "target_qualification": None, "prefecture": "東京都"},
    {"school": "東京デザインテクノロジーセンター", "name": "WebデザイナーAIコース",        "field": "IT", "benefit_type": "専門実践", "benefit_rate": 70, "price": 660000, "duration": "12か月", "format": "通学", "target_qualification": None, "prefecture": "東京都"},
    # ── 資格の大原 ──
    {"school": "資格の大原", "name": "簿記検定合格コース（2・3級W合格）",  "field": "会計", "benefit_type": "一般", "benefit_rate": 20, "price": 88000,  "duration": "6か月",  "format": "通学・通信", "target_qualification": "日商簿記2級"},
    {"school": "資格の大原", "name": "税理士講座（簿記論）",               "field": "会計", "benefit_type": "一般", "benefit_rate": 20, "price": 132000, "duration": "12か月", "format": "通学・通信", "target_qualification": "税理士"},
    {"school": "資格の大原", "name": "税理士講座（財務諸表論）",           "field": "会計", "benefit_type": "一般", "benefit_rate": 20, "price": 132000, "duration": "12か月", "format": "通学・通信", "target_qualification": "税理士"},
    {"school": "資格の大原", "name": "税理士講座（法人税法）",             "field": "会計", "benefit_type": "一般", "benefit_rate": 20, "price": 132000, "duration": "12か月", "format": "通学・通信", "target_qualification": "税理士"},
    {"school": "資格の大原", "name": "公認会計士講座",                     "field": "会計", "benefit_type": "一般", "benefit_rate": 20, "price": 715000, "duration": "24か月", "format": "通学・通信", "target_qualification": "公認会計士"},
    {"school": "資格の大原", "name": "社会保険労務士講座",                 "field": "法務", "benefit_type": "一般", "benefit_rate": 20, "price": 110000, "duration": "12か月", "format": "通学・通信", "target_qualification": "社会保険労務士"},
    {"school": "資格の大原", "name": "行政書士講座",                       "field": "法務", "benefit_type": "一般", "benefit_rate": 20, "price": 77000,  "duration": "12か月", "format": "通学・通信", "target_qualification": "行政書士"},
    {"school": "資格の大原", "name": "宅地建物取引士講座",                 "field": "不動産", "benefit_type": "一般", "benefit_rate": 20, "price": 77000,  "duration": "12か月", "format": "通学・通信", "target_qualification": "宅地建物取引士"},
    {"school": "資格の大原", "name": "FP技能士講座（2・3級）",             "field": "会計", "benefit_type": "一般", "benefit_rate": 20, "price": 66000,  "duration": "6か月",  "format": "通学・通信", "target_qualification": "FP2級"},
    {"school": "資格の大原", "name": "中小企業診断士講座",                 "field": "経営", "benefit_type": "一般", "benefit_rate": 20, "price": 275000, "duration": "18か月", "format": "通学・通信", "target_qualification": "中小企業診断士"},
    {"school": "資格の大原", "name": "司法書士講座",                       "field": "法務", "benefit_type": "一般", "benefit_rate": 20, "price": 396000, "duration": "24か月", "format": "通学・通信", "target_qualification": "司法書士"},
    # ── 大栄 ──
    {"school": "大栄", "name": "宅建士合格講座",                "field": "不動産", "benefit_type": "一般", "benefit_rate": 20, "price": 88000,  "duration": "12か月", "format": "通学", "target_qualification": "宅地建物取引士"},
    {"school": "大栄", "name": "簿記検定試験対策講座（2・3級）","field": "会計",   "benefit_type": "一般", "benefit_rate": 20, "price": 77000,  "duration": "6か月",  "format": "通学", "target_qualification": "日商簿記2級"},
    {"school": "大栄", "name": "FP技能士試験対策講座",          "field": "会計",   "benefit_type": "一般", "benefit_rate": 20, "price": 66000,  "duration": "6か月",  "format": "通学", "target_qualification": "FP2級"},
    {"school": "大栄", "name": "行政書士試験対策講座",          "field": "法務",   "benefit_type": "一般", "benefit_rate": 20, "price": 88000,  "duration": "12か月", "format": "通学", "target_qualification": "行政書士"},
    {"school": "大栄", "name": "社労士試験対策講座",            "field": "法務",   "benefit_type": "一般", "benefit_rate": 20, "price": 99000,  "duration": "12か月", "format": "通学", "target_qualification": "社会保険労務士"},
    {"school": "大栄", "name": "マンション管理士・管理業務主任者講座","field": "不動産","benefit_type": "一般","benefit_rate": 20,"price": 88000, "duration": "12か月", "format": "通学", "target_qualification": "マンション管理士"},
    # ── 東京CPA会計学院 ──
    {"school": "東京CPA会計学院", "name": "公認会計士講座（全科目）",  "field": "会計", "benefit_type": "一般", "benefit_rate": 20, "price": 748000, "duration": "24か月", "format": "通学・通信", "target_qualification": "公認会計士", "prefecture": "東京都"},
    {"school": "東京CPA会計学院", "name": "税理士講座（簿記論・財務諸表論）","field": "会計","benefit_type": "一般","benefit_rate": 20,"price": 198000,"duration": "12か月","format": "通学・通信", "target_qualification": "税理士", "prefecture": "東京都"},
    {"school": "東京CPA会計学院", "name": "USCPA講座",              "field": "会計", "benefit_type": "一般", "benefit_rate": 20, "price": 550000, "duration": "24か月", "format": "通学・オンライン", "target_qualification": "米国公認会計士", "prefecture": "東京都"},
    # ── ECC外語学院 ──
    {"school": "ECC外語学院", "name": "社会人向け英会話コース",          "field": "語学", "benefit_type": "一般", "benefit_rate": 20, "price": 165000, "duration": "12か月", "format": "通学", "target_qualification": None},
    {"school": "ECC外語学院", "name": "TOEIC対策スピードマスターコース", "field": "語学", "benefit_type": "一般", "benefit_rate": 20, "price": 110000, "duration": "6か月",  "format": "通学", "target_qualification": "TOEIC L&R"},
    {"school": "ECC外語学院", "name": "英検対策コース（準1級）",         "field": "語学", "benefit_type": "一般", "benefit_rate": 20, "price": 99000,  "duration": "6か月",  "format": "通学", "target_qualification": "実用英語技能検定（英検）準1級"},
    # ── ベルリッツ ──
    {"school": "ベルリッツ", "name": "ビジネス英語プログラム（初中級）", "field": "語学", "benefit_type": "一般", "benefit_rate": 20, "price": 330000, "duration": "6か月",  "format": "通学", "target_qualification": None},
    {"school": "ベルリッツ", "name": "TOEIC対策プログラム",            "field": "語学", "benefit_type": "一般", "benefit_rate": 20, "price": 165000, "duration": "6か月",  "format": "通学・オンライン", "target_qualification": "TOEIC L&R"},
    {"school": "ベルリッツ", "name": "英語マルチレベルグループコース",  "field": "語学", "benefit_type": "一般", "benefit_rate": 20, "price": 220000, "duration": "12か月", "format": "通学", "target_qualification": None},
    # ── NOVA ──
    {"school": "NOVA", "name": "英会話スタンダードコース",     "field": "語学", "benefit_type": "一般", "benefit_rate": 20, "price": 132000, "duration": "12か月", "format": "通学", "target_qualification": None},
    {"school": "NOVA", "name": "英会話ビジネスコース",         "field": "語学", "benefit_type": "一般", "benefit_rate": 20, "price": 165000, "duration": "12か月", "format": "通学・オンライン", "target_qualification": None},
    # ── TBC英語スクール ──
    {"school": "TBC英語スクール", "name": "TOEIC L&R TEST 特訓講座（スコアアップコース）","field": "語学","benefit_type": "一般","benefit_rate": 20,"price": 88000,"duration": "3か月","format": "通学・オンライン","target_qualification": "TOEIC L&R"},
    {"school": "TBC英語スクール", "name": "TOEIC L&R TEST 目指せ730・860点コース",       "field": "語学","benefit_type": "一般","benefit_rate": 20,"price": 110000,"duration": "6か月","format": "通学・オンライン","target_qualification": "TOEIC L&R"},
    # ── 三幸福祉カレッジ ──
    {"school": "三幸福祉カレッジ", "name": "介護職員初任者研修",                 "field": "介護", "benefit_type": "特定一般", "benefit_rate": 40, "price": 87780, "duration": "3か月",  "format": "通学・通信", "target_qualification": "介護職員初任者研修"},
    {"school": "三幸福祉カレッジ", "name": "介護福祉士実務者研修",               "field": "介護", "benefit_type": "特定一般", "benefit_rate": 40, "price": 77000, "duration": "6か月",  "format": "通学・通信", "target_qualification": "介護福祉士実務者研修"},
    {"school": "三幸福祉カレッジ", "name": "介護福祉士受験対策講座",             "field": "介護", "benefit_type": "一般",    "benefit_rate": 20, "price": 44000, "duration": "3か月",  "format": "通学",       "target_qualification": "介護福祉士"},
    {"school": "三幸福祉カレッジ", "name": "ケアマネージャー試験対策講座",       "field": "介護", "benefit_type": "一般",    "benefit_rate": 20, "price": 55000, "duration": "4か月",  "format": "通学",       "target_qualification": "介護支援専門員"},
    {"school": "三幸福祉カレッジ", "name": "サービス提供責任者研修（実務者研修）","field": "介護", "benefit_type": "特定一般", "benefit_rate": 40, "price": 66000, "duration": "4か月",  "format": "通学・通信", "target_qualification": "介護福祉士実務者研修"},
    # ── 日本医療事務協会 ──
    {"school": "日本医療事務協会", "name": "医療事務講座（通信）",           "field": "医療", "benefit_type": "一般", "benefit_rate": 20, "price": 49500,  "duration": "4か月",  "format": "通信",  "target_qualification": "医療事務技能審査試験（メディカルクラーク）"},
    {"school": "日本医療事務協会", "name": "医療事務講座（通学）",           "field": "医療", "benefit_type": "一般", "benefit_rate": 20, "price": 55000,  "duration": "3か月",  "format": "通学",  "target_qualification": "医療事務技能審査試験（メディカルクラーク）"},
    {"school": "日本医療事務協会", "name": "調剤薬局事務講座",               "field": "医療", "benefit_type": "一般", "benefit_rate": 20, "price": 38500,  "duration": "3か月",  "format": "通信",  "target_qualification": "調剤事務管理士"},
    {"school": "日本医療事務協会", "name": "歯科医療事務講座",               "field": "医療", "benefit_type": "一般", "benefit_rate": 20, "price": 44000,  "duration": "3か月",  "format": "通信",  "target_qualification": "歯科医療事務管理士"},
    {"school": "日本医療事務協会", "name": "診療報酬請求事務能力認定試験講座","field": "医療", "benefit_type": "一般", "benefit_rate": 20, "price": 66000,  "duration": "6か月",  "format": "通信",  "target_qualification": "診療報酬請求事務能力認定試験"},
    # ── ソラスト ──
    {"school": "ソラスト", "name": "医療事務（医科）通学コース",       "field": "医療", "benefit_type": "一般", "benefit_rate": 20, "price": 49500,  "duration": "3か月",  "format": "通学", "target_qualification": "医療事務技能審査試験（メディカルクラーク）"},
    {"school": "ソラスト", "name": "医療事務（医科）通信コース",       "field": "医療", "benefit_type": "一般", "benefit_rate": 20, "price": 44000,  "duration": "4か月",  "format": "通信", "target_qualification": "医療事務技能審査試験（メディカルクラーク）"},
    {"school": "ソラスト", "name": "調剤薬局事務通学コース",           "field": "医療", "benefit_type": "一般", "benefit_rate": 20, "price": 38500,  "duration": "2か月",  "format": "通学", "target_qualification": "調剤事務管理士"},
    {"school": "ソラスト", "name": "介護職員初任者研修",               "field": "介護", "benefit_type": "特定一般", "benefit_rate": 40, "price": 82500, "duration": "3か月", "format": "通学", "target_qualification": "介護職員初任者研修"},
    # ── ヒューマンアカデミー ──
    {"school": "ヒューマンアカデミー", "name": "キャリアコンサルタント養成講座",          "field": "キャリア", "benefit_type": "特定一般", "benefit_rate": 40, "price": 330000, "duration": "6か月",  "format": "通学・オンライン", "target_qualification": "キャリアコンサルタント"},
    {"school": "ヒューマンアカデミー", "name": "日本語教師養成講座（420時間）",           "field": "キャリア", "benefit_type": "特定一般", "benefit_rate": 40, "price": 495000, "duration": "12か月", "format": "通学",           "target_qualification": "日本語教育能力検定試験"},
    {"school": "ヒューマンアカデミー", "name": "Webデザイン講座（Web制作コース）",        "field": "IT",       "benefit_type": "一般",    "benefit_rate": 20, "price": 275000, "duration": "6か月",  "format": "通学・オンライン", "target_qualification": "ウェブデザイン技能検定"},
    {"school": "ヒューマンアカデミー", "name": "医療事務総合講座",                        "field": "医療",     "benefit_type": "一般",    "benefit_rate": 20, "price": 132000, "duration": "6か月",  "format": "通信",           "target_qualification": "医療事務技能審査試験（メディカルクラーク）"},
    {"school": "ヒューマンアカデミー", "name": "保育士完全合格講座",                      "field": "キャリア", "benefit_type": "一般",    "benefit_rate": 20, "price": 99000,  "duration": "12か月", "format": "通信",           "target_qualification": "保育士"},
    {"school": "ヒューマンアカデミー", "name": "ペットトリマー・動物看護師コース",         "field": "キャリア", "benefit_type": "一般",    "benefit_rate": 20, "price": 385000, "duration": "12か月", "format": "通学",           "target_qualification": None},
    {"school": "ヒューマンアカデミー", "name": "Pythonプログラミングコース",               "field": "IT",       "benefit_type": "一般",    "benefit_rate": 20, "price": 198000, "duration": "6か月",  "format": "オンライン",     "target_qualification": "Python 3 エンジニア認定基礎試験"},
    # ── 日本マンパワー ──
    {"school": "日本マンパワー", "name": "キャリアコンサルタント養成講座（標準）",      "field": "キャリア", "benefit_type": "特定一般", "benefit_rate": 40, "price": 308000, "duration": "6か月",  "format": "通学・通信", "target_qualification": "キャリアコンサルタント"},
    {"school": "日本マンパワー", "name": "キャリアコンサルタント養成講座（オンライン）","field": "キャリア", "benefit_type": "特定一般", "benefit_rate": 40, "price": 308000, "duration": "6か月",  "format": "オンライン", "target_qualification": "キャリアコンサルタント"},
    {"school": "日本マンパワー", "name": "国家資格キャリアコンサルタント更新講習",      "field": "キャリア", "benefit_type": "一般",    "benefit_rate": 20, "price": 33000,  "duration": "1か月",  "format": "オンライン", "target_qualification": "キャリアコンサルタント"},
    # ── コヤマドライビングスクール（方式4）──
    {"school": "コヤマドライビングスクール", "name": "普通自動車二種免許取得コース", "field": "キャリア", "benefit_type": "特定一般", "benefit_rate": 40, "price": 250000, "duration": "2か月",  "format": "通学", "target_qualification": "普通自動車第二種免許", "prefecture": "東京都"},
    {"school": "コヤマドライビングスクール", "name": "大型自動車免許取得コース",     "field": "キャリア", "benefit_type": "特定一般", "benefit_rate": 40, "price": 380000, "duration": "2か月",  "format": "通学", "target_qualification": "大型自動車第一種免許", "prefecture": "東京都"},
    {"school": "コヤマドライビングスクール", "name": "大型自動車二種免許取得コース", "field": "キャリア", "benefit_type": "特定一般", "benefit_rate": 40, "price": 480000, "duration": "2か月",  "format": "通学", "target_qualification": "大型自動車第二種免許", "prefecture": "東京都"},
    {"school": "コヤマドライビングスクール", "name": "フォークリフト運転技能者講習", "field": "キャリア", "benefit_type": "一般",    "benefit_rate": 20, "price": 55000,  "duration": "1か月",  "format": "通学", "target_qualification": "フォークリフト運転技能者", "prefecture": "東京都"},
    # ── KDS関東自動車学校（方式4）──
    {"school": "KDS関東自動車学校", "name": "大型自動車免許コース",            "field": "キャリア", "benefit_type": "特定一般", "benefit_rate": 40, "price": 360000, "duration": "2か月",  "format": "通学", "target_qualification": "大型自動車第一種免許", "prefecture": "神奈川県"},
    {"school": "KDS関東自動車学校", "name": "大型自動車二種免許コース",        "field": "キャリア", "benefit_type": "特定一般", "benefit_rate": 40, "price": 450000, "duration": "2か月",  "format": "通学", "target_qualification": "大型自動車第二種免許", "prefecture": "神奈川県"},
    {"school": "KDS関東自動車学校", "name": "中型自動車免許コース",            "field": "キャリア", "benefit_type": "一般",    "benefit_rate": 20, "price": 250000, "duration": "1か月",  "format": "通学", "target_qualification": "中型自動車第一種免許", "prefecture": "神奈川県"},
    # ── グロービス経営大学院（方式6）──
    {"school": "グロービス経営大学院", "name": "MBA（経営学修士）全研究科",        "field": "経営", "benefit_type": "専門実践", "benefit_rate": 70, "price": 3168000, "duration": "24か月", "format": "通学・オンライン", "target_qualification": "MBA（経営学修士）", "prefecture": "全国"},
    {"school": "グロービス経営大学院", "name": "MBA単科コース（クリティカルシンキング等）","field": "経営","benefit_type": "一般","benefit_rate": 20,"price": 99000,"duration": "3か月","format": "通学・オンライン","target_qualification": None},
    # ── 早稲田大学ビジネス・スクール（方式6）──
    {"school": "早稲田大学ビジネス・スクール", "name": "経営管理研究科（MBA・夜間主）", "field": "経営", "benefit_type": "専門実践", "benefit_rate": 70, "price": 3000000, "duration": "24か月", "format": "通学",     "target_qualification": "MBA（経営学修士）", "prefecture": "東京都"},
    {"school": "早稲田大学ビジネス・スクール", "name": "経営管理研究科（MBA・昼間主）", "field": "経営", "benefit_type": "専門実践", "benefit_rate": 70, "price": 3000000, "duration": "24か月", "format": "通学",     "target_qualification": "MBA（経営学修士）", "prefecture": "東京都"},
    # ── BBT大学院大学（方式6）──
    {"school": "BBT大学院大学", "name": "経営管理研究科（グローバルリーダーシップ専攻）","field": "経営","benefit_type": "専門実践","benefit_rate": 70,"price": 2200000,"duration": "24か月","format": "オンライン","target_qualification": "MBA（経営学修士）"},
]


# ─────────────────────────────────────────
# 方式3: 資格マスターデータ
# ─────────────────────────────────────────
QUALIFICATIONS = [
    # IT
    {"name": "ITパスポート",               "name_kana": "あいてぃーぱすぽーと",      "field": "IT",    "category_slug": "it",         "qual_type": "国家資格", "difficulty": 1, "pass_rate": 50.0, "exam_fee": 7500,   "exam_schedule": "随時（CBT方式）",  "official_url": "https://www3.jitec.ipa.go.jp/", "description": "IPA（情報処理推進機構）が実施するIT入門資格。システムやITサービスの基礎知識を問う。"},
    {"name": "基本情報技術者",             "name_kana": "きほんじょうほうぎじゅつしゃ","field": "IT",    "category_slug": "it",         "qual_type": "国家資格", "difficulty": 2, "pass_rate": 30.0, "exam_fee": 8000,   "exam_schedule": "随時（CBT方式）",  "official_url": "https://www3.jitec.ipa.go.jp/", "description": "IPAが実施するIT系エンジニアの登竜門資格。プログラミングやアルゴリズムの知識が必要。"},
    {"name": "応用情報技術者",             "name_kana": "おうようじょうほうぎじゅつしゃ","field": "IT",   "category_slug": "it",         "qual_type": "国家資格", "difficulty": 3, "pass_rate": 25.0, "exam_fee": 8000,   "exam_schedule": "年2回（春・秋）",  "official_url": "https://www3.jitec.ipa.go.jp/", "description": "基本情報技術者の上位資格。設計・開発・運用など幅広いITスキルが問われる。"},
    {"name": "ネットワークスペシャリスト", "name_kana": "ねっとわーくすぺしゃりすと",  "field": "IT",    "category_slug": "it",         "qual_type": "国家資格", "difficulty": 4, "pass_rate": 14.0, "exam_fee": 8000,   "exam_schedule": "年1回（秋）",      "official_url": "https://www3.jitec.ipa.go.jp/", "description": "ネットワーク構築・運用の高度な知識と技術を持つ専門家の国家資格。"},
    {"name": "データベーススペシャリスト", "name_kana": "でーたべーすすぺしゃりすと",  "field": "IT",    "category_slug": "it",         "qual_type": "国家資格", "difficulty": 4, "pass_rate": 14.0, "exam_fee": 8000,   "exam_schedule": "年1回（春）",      "official_url": "https://www3.jitec.ipa.go.jp/", "description": "データベース設計・管理の高度な専門知識を証明する国家資格。"},
    {"name": "プロジェクトマネージャ",     "name_kana": "ぷろじぇくとまねーじゃ",      "field": "IT",    "category_slug": "it",         "qual_type": "国家資格", "difficulty": 5, "pass_rate": 13.0, "exam_fee": 8000,   "exam_schedule": "年1回（秋）",      "official_url": "https://www3.jitec.ipa.go.jp/", "description": "プロジェクト計画・管理の高度な専門知識を証明するIPA最高峰資格の一つ。"},
    {"name": "G検定（ジェネラリスト検定）","name_kana": "じーけんてい",               "field": "AI",    "category_slug": "it",         "qual_type": "民間資格", "difficulty": 2, "pass_rate": 65.0, "exam_fee": 13200,  "exam_schedule": "年3回程度",        "official_url": "https://www.jdla.org/",          "description": "日本ディープラーニング協会が実施するAI・ディープラーニングの一般知識を問う資格。"},
    {"name": "E資格（エンジニア資格）",    "name_kana": "いーしかく",                 "field": "AI",    "category_slug": "it",         "qual_type": "民間資格", "difficulty": 4, "pass_rate": 70.0, "exam_fee": 33000,  "exam_schedule": "年2回（2月・8月）","official_url": "https://www.jdla.org/",          "description": "日本ディープラーニング協会が実施するAIエンジニア向け資格。ディープラーニング技術の実装能力を問う。"},
    {"name": "AWS認定ソリューションアーキテクト（アソシエイト）","name_kana": "えーだぶりゅーえすにんてい","field": "IT","category_slug": "it","qual_type": "ベンダー資格","difficulty": 3,"pass_rate": None,"exam_fee": 20000,"exam_schedule": "随時（テストセンター）","official_url": "https://aws.amazon.com/jp/certification/","description": "AWSクラウドのアーキテクト設計・デプロイ能力を証明するベンダー資格。"},
    {"name": "ウェブデザイン技能検定",     "name_kana": "うぇぶでざいんぎのうけんてい", "field": "IT",    "category_slug": "it",         "qual_type": "国家資格", "difficulty": 2, "pass_rate": 40.0, "exam_fee": 8000,   "exam_schedule": "年4回",            "official_url": "https://www.webdesign.or.jp/",   "description": "Webデザインに関する技能を問う唯一の国家検定。1級〜3級あり。"},
    # 会計
    {"name": "日商簿記3級",               "name_kana": "にっしょうぼきさんきゅう",     "field": "会計",  "category_slug": "accounting", "qual_type": "民間資格", "difficulty": 1, "pass_rate": 45.0, "exam_fee": 2850,   "exam_schedule": "年3回（6月・11月・2月）+CBT随時","official_url": "https://www.kentei.ne.jp/","description": "日本商工会議所が実施する簿記検定の入門レベル。経理・会計の基礎を学べる。"},
    {"name": "日商簿記2級",               "name_kana": "にっしょうぼきにきゅう",       "field": "会計",  "category_slug": "accounting", "qual_type": "民間資格", "difficulty": 3, "pass_rate": 25.0, "exam_fee": 4720,   "exam_schedule": "年3回（6月・11月・2月）+CBT随時","official_url": "https://www.kentei.ne.jp/","description": "企業の経理や財務に必要な知識を証明する、転職市場で需要が高い資格。"},
    {"name": "日商簿記1級",               "name_kana": "にっしょうぼきいっきゅう",     "field": "会計",  "category_slug": "accounting", "qual_type": "民間資格", "difficulty": 5, "pass_rate": 10.0, "exam_fee": 8800,   "exam_schedule": "年2回（6月・11月）",              "official_url": "https://www.kentei.ne.jp/","description": "商業簿記・会計学・工業簿記・原価計算を網羅した最高難度の簿記資格。税理士試験の受験資格にもなる。"},
    {"name": "FP3級（ファイナンシャルプランナー3級）","name_kana": "えふぴーさんきゅう","field": "会計","category_slug": "accounting","qual_type": "国家資格","difficulty": 1,"pass_rate": 80.0,"exam_fee": 4000,"exam_schedule": "年3回（5月・9月・1月）","official_url": "https://www.jafp.or.jp/","description": "お金に関する総合的な知識を問う国家資格の入門編。ライフプランや税金の基礎が学べる。"},
    {"name": "FP2級（ファイナンシャルプランナー2級）","name_kana": "えふぴーにきゅう","field": "会計","category_slug": "accounting","qual_type": "国家資格","difficulty": 2,"pass_rate": 50.0,"exam_fee": 6000,"exam_schedule": "年3回（5月・9月・1月）","official_url": "https://www.jafp.or.jp/","description": "実務で活かせるレベルのFP資格。転職や相談業務に活用できる。"},
    {"name": "税理士",                     "name_kana": "ぜいりし",                   "field": "会計",  "category_slug": "accounting", "qual_type": "国家資格", "difficulty": 5, "pass_rate": 15.0, "exam_fee": 4000,   "exam_schedule": "年1回（8月）",     "official_url": "https://www.nta.go.jp/",          "description": "税務申告・相談のプロ国家資格。11科目から5科目に合格が必要な難関資格。"},
    {"name": "公認会計士",                 "name_kana": "こうにんかいけいし",           "field": "会計",  "category_slug": "accounting", "qual_type": "国家資格", "difficulty": 5, "pass_rate": 10.0, "exam_fee": 19500,  "exam_schedule": "年1回（短答式：5月・12月）","official_url": "https://www.fsa.go.jp/","description": "監査・会計のトップ国家資格。三大国家資格の一つとされる難関資格。"},
    {"name": "中小企業診断士",             "name_kana": "ちゅうしょうきぎょうしんだんし","field": "経営",  "category_slug": "business",   "qual_type": "国家資格", "difficulty": 4, "pass_rate": 4.0,  "exam_fee": 14200,  "exam_schedule": "年1回（1次：8月、2次：10月）","official_url": "https://www.j-smeca.jp/","description": "経営コンサルタントの国家資格。1次試験（マーク式）と2次試験（記述式・口述）の2段階。"},
    # 法務
    {"name": "社会保険労務士",             "name_kana": "しゃかいほけんろうむし",       "field": "法務",  "category_slug": "legal",      "qual_type": "国家資格", "difficulty": 4, "pass_rate": 6.0,  "exam_fee": 15000,  "exam_schedule": "年1回（8月）",     "official_url": "https://www.sharosi-siken.or.jp/","description": "労働・社会保険に関する申請・相談業務を行う国家資格。企業の人事・総務で重宝される。"},
    {"name": "行政書士",                   "name_kana": "ぎょうせいしょし",             "field": "法務",  "category_slug": "legal",      "qual_type": "国家資格", "difficulty": 3, "pass_rate": 12.0, "exam_fee": 10400,  "exam_schedule": "年1回（11月）",    "official_url": "https://gyosei-shiken.or.jp/",    "description": "官公署への書類作成・申請代行を行う国家資格。独立開業が可能。"},
    {"name": "司法書士",                   "name_kana": "しほうしょし",                 "field": "法務",  "category_slug": "legal",      "qual_type": "国家資格", "difficulty": 5, "pass_rate": 4.0,  "exam_fee": 8000,   "exam_schedule": "年1回（7月）",     "official_url": "https://www.moj.go.jp/",          "description": "不動産登記・法人登記など法律書類の作成を専門とする国家資格。"},
    {"name": "キャリアコンサルタント",     "name_kana": "きゃりあこんさるたんと",       "field": "キャリア","category_slug": "legal",      "qual_type": "国家資格", "difficulty": 2, "pass_rate": 60.0, "exam_fee": 8900,   "exam_schedule": "年3回（3月・7月・11月）","official_url": "https://www.mhlw.go.jp/","description": "就職・転職・キャリア形成の相談を行う国家資格。企業・学校・ハローワークで活躍。"},
    # 不動産
    {"name": "宅地建物取引士",             "name_kana": "たくちたてものとりひきし",     "field": "不動産","category_slug": "estate",     "qual_type": "国家資格", "difficulty": 3, "pass_rate": 15.0, "exam_fee": 8200,   "exam_schedule": "年1回（10月）",    "official_url": "https://www.retio.or.jp/",        "description": "不動産取引に必要な国家資格。不動産業者に5人に1人以上の設置が義務付けられている。"},
    {"name": "マンション管理士",           "name_kana": "まんしょんかんりし",           "field": "不動産","category_slug": "estate",     "qual_type": "国家資格", "difficulty": 4, "pass_rate": 8.0,  "exam_fee": 9400,   "exam_schedule": "年1回（11月）",    "official_url": "https://www.mankan.org/",         "description": "マンション管理組合の運営をサポートする国家資格。区分所有法・管理規約などの知識が必要。"},
    {"name": "管理業務主任者",             "name_kana": "かんりぎょうむしゅにんしゃ",   "field": "不動産","category_slug": "estate",     "qual_type": "国家資格", "difficulty": 3, "pass_rate": 22.0, "exam_fee": 8900,   "exam_schedule": "年1回（12月）",    "official_url": "https://www.kanrikyo.or.jp/",     "description": "マンション管理会社の必置資格。30管理組合に1名以上の設置が法律で義務付けられている。"},
    {"name": "賃貸不動産経営管理士",       "name_kana": "ちんたいふどうさんけいえいかんりし","field": "不動産","category_slug": "estate","qual_type": "国家資格","difficulty": 2,"pass_rate": 30.0,"exam_fee": 13200,"exam_schedule": "年1回（11月）","official_url": "https://www.chintaikanrishi.jp/","description": "賃貸住宅管理業者の業務管理者として活躍できる国家資格（2021年国家資格化）。"},
    # 語学
    {"name": "実用英語技能検定（英検）準2級","name_kana": "えいけんじゅんにきゅう",    "field": "語学",  "category_slug": "english",    "qual_type": "民間資格", "difficulty": 2, "pass_rate": 50.0, "exam_fee": 6400,   "exam_schedule": "年3回（1次：6月・10月・1月）","official_url": "https://www.eiken.or.jp/","description": "日常的な英語の読み書き・会話ができるレベルの英検資格。高校在学程度の英語力。"},
    {"name": "実用英語技能検定（英検）2級", "name_kana": "えいけんにきゅう",            "field": "語学",  "category_slug": "english",    "qual_type": "民間資格", "difficulty": 3, "pass_rate": 35.0, "exam_fee": 8400,   "exam_schedule": "年3回（1次：6月・10月・1月）","official_url": "https://www.eiken.or.jp/","description": "海外旅行・留学などで必要な英語力を証明する英検の中核資格。高校卒業程度の英語力。"},
    {"name": "実用英語技能検定（英検）準1級","name_kana": "えいけんじゅんいっきゅう",   "field": "語学",  "category_slug": "english",    "qual_type": "民間資格", "difficulty": 4, "pass_rate": 20.0, "exam_fee": 10500,  "exam_schedule": "年3回（1次：6月・10月・1月）","official_url": "https://www.eiken.or.jp/","description": "ビジネスで通用する英語力を証明する英検の上位資格。大学中級程度の英語力。"},
    {"name": "TOEIC L&R（リスニング・リーディング）","name_kana": "とーいっく",          "field": "語学",  "category_slug": "english",    "qual_type": "民間資格", "difficulty": 2, "pass_rate": None, "exam_fee": 7810,   "exam_schedule": "年10回",           "official_url": "https://www.iibc-global.org/",    "description": "英語の聞く・読む力を測るグローバルスタンダードのテスト。企業採用・昇進の目安として広く活用される。"},
    # 医療介護
    {"name": "医療事務技能審査試験（メディカルクラーク）","name_kana": "めでぃかるくらーく","field": "医療","category_slug": "medical","qual_type": "民間資格","difficulty": 2,"pass_rate": 55.0,"exam_fee": 6900,"exam_schedule": "毎月1回（在宅受験）","official_url": "https://www.ima.or.jp/","description": "医療事務の実務能力を証明する資格。レセプト作成・窓口業務などの知識を問う。"},
    {"name": "診療報酬請求事務能力認定試験","name_kana": "しんりょうほうしゅうせいきゅうじむのうりょくにんていしけん","field": "医療","category_slug": "medical","qual_type": "民間資格","difficulty": 3,"pass_rate": 30.0,"exam_fee": 6900,"exam_schedule": "年2回（7月・12月）","official_url": "https://www.iryojimu.or.jp/","description": "医科・歯科の診療報酬請求（レセプト）事務の最上位民間資格。医療機関で高く評価される。"},
    {"name": "介護職員初任者研修",         "name_kana": "かいごしょくいんしょにんしゃけんしゅう","field": "介護","category_slug": "medical","qual_type": "公的資格","difficulty": 1,"pass_rate": 95.0,"exam_fee": None,"exam_schedule": "随時（スクール受講後に修了試験）","official_url": "https://www.mhlw.go.jp/","description": "介護職の入門資格（旧ヘルパー2級）。訪問介護事業所等での身体介護業務に必要。"},
    {"name": "介護福祉士実務者研修",       "name_kana": "かいごふくしししつむしゃけんしゅう","field": "介護","category_slug": "medical","qual_type": "公的資格","difficulty": 2,"pass_rate": 90.0,"exam_fee": None,"exam_schedule": "随時（スクール受講後に修了試験）","official_url": "https://www.mhlw.go.jp/","description": "介護福祉士国家試験の受験資格に必要な研修。介護のリーダー的存在を目指す人向け。"},
    {"name": "介護福祉士",                 "name_kana": "かいごふくしし",               "field": "介護",  "category_slug": "medical",    "qual_type": "国家資格", "difficulty": 3, "pass_rate": 70.0, "exam_fee": 17200,  "exam_schedule": "年1回（1月）",     "official_url": "https://www.sssc.or.jp/",         "description": "介護の専門的知識・技術を証明する国家資格。キャリアアップや処遇改善に直結する。"},
    {"name": "介護支援専門員（ケアマネージャー）","name_kana": "けあまねーじゃー","field": "介護","category_slug": "medical","qual_type": "公的資格","difficulty": 4,"pass_rate": 20.0,"exam_fee": 6700,"exam_schedule": "年1回（10月）","official_url": "https://www.mhlw.go.jp/","description": "要介護者の介護サービス計画（ケアプラン）を作成する専門職。5年以上の実務経験が必要。"},
    {"name": "看護師",                     "name_kana": "かんごし",                     "field": "医療",  "category_slug": "medical",    "qual_type": "国家資格", "difficulty": 3, "pass_rate": 90.0, "exam_fee": 5400,   "exam_schedule": "年1回（2月）",     "official_url": "https://www.nurse.or.jp/",        "description": "病院・クリニックなどで医師の補助と患者のケアを行う医療職の国家資格。"},
    {"name": "保育士",                     "name_kana": "ほいくし",                     "field": "キャリア","category_slug": "legal",      "qual_type": "国家資格", "difficulty": 3, "pass_rate": 20.0, "exam_fee": 12700,  "exam_schedule": "年2回（4月・10月）","official_url": "https://www.hoyokyo.or.jp/","description": "保育所・幼稚園などで子どもの保育を行う国家資格。"},
    {"name": "日本語教育能力検定試験",     "name_kana": "にほんごきょういくのうりょくけんていしけん","field": "キャリア","category_slug": "legal","qual_type": "民間資格","difficulty": 3,"pass_rate": 30.0,"exam_fee": 11000,"exam_schedule": "年1回（10月）","official_url": "https://www.jees.or.jp/","description": "日本語教師としての専門知識・能力を証明する資格。外国語としての日本語教授法を問う。"},
    # 運転免許（方式4）
    {"name": "大型自動車第一種免許",       "name_kana": "おおがたじどうしゃだいいっしゅめんきょ","field": "キャリア","category_slug": "legal","qual_type": "国家資格","difficulty": 3,"pass_rate": None,"exam_fee": 3400,"exam_schedule": "随時（教習所修了後）","official_url": "https://www.mlit.go.jp/","description": "大型トラック・バスなどの運転に必要な免許。物流業界でのキャリアアップに不可欠。"},
    {"name": "大型自動車第二種免許",       "name_kana": "おおがたじどうしゃだいにしゅめんきょ","field": "キャリア","category_slug": "legal","qual_type": "国家資格","difficulty": 4,"pass_rate": None,"exam_fee": 3400,"exam_schedule": "随時（教習所修了後）","official_url": "https://www.mlit.go.jp/","description": "路線バス・観光バスなどの旅客運送に必要な免許。バス運転手・観光ガイドドライバーとして活躍できる。"},
    {"name": "フォークリフト運転技能者",   "name_kana": "ふぉーくりふとうんてんぎのうしゃ","field": "キャリア","category_slug": "legal","qual_type": "国家資格","difficulty": 1,"pass_rate": 95.0,"exam_fee": 40000,"exam_schedule": "随時（各機関）","official_url": "https://www.mhlw.go.jp/","description": "フォークリフトの運転操作資格。倉庫・工場・物流センターでの業務に必須。"},
    # MBA
    {"name": "MBA（経営学修士）",          "name_kana": "えむびーえー",                 "field": "経営",  "category_slug": "business",   "qual_type": "学位",     "difficulty": 5, "pass_rate": None, "exam_fee": None,  "exam_schedule": "各大学院の選考による",   "official_url": None,                             "description": "経営管理・マーケティング・会計・リーダーシップなど経営全般を学ぶ大学院学位。専門実践教育訓練給付金の対象となるケースが多い。"},
]


# ─────────────────────────────────────────
# 方式8: 自治体独自給付金
# ─────────────────────────────────────────
LOCAL_BENEFITS = [
    {"prefecture": "東京都", "name": "TOKYOかいごチャレンジ", "max_amount": 300000,
     "target": "介護職未経験者・離職者",
     "description": "東京都が実施する介護人材確保のための支援制度。介護職員初任者研修・実務者研修の受講料を全額補助（上限30万円）。",
     "fields": "介護",
     "url": "https://www.fukushihoken.metro.tokyo.lg.jp/"},
    {"prefecture": "東京都", "name": "東京都技能者育成基金（ものづくり補助金）", "max_amount": 200000,
     "target": "ものづくり分野の技能者・求職者",
     "description": "東京都が実施するものづくり分野の技術・技能習得支援。職業訓練校・技能訓練センターでの訓練費用を補助。",
     "fields": "IT・キャリア",
     "url": "https://www.metro.tokyo.lg.jp/"},
    {"prefecture": "大阪府", "name": "大阪府スキルアップ助成金（中小企業人材育成）", "max_amount": 500000,
     "target": "大阪府内中小企業在籍の従業員",
     "description": "大阪府内の中小企業従業員が資格取得・研修受講した際の費用を補助。教育訓練給付金と併用可能な場合もある。",
     "fields": "全分野",
     "url": "https://www.pref.osaka.lg.jp/"},
    {"prefecture": "神奈川県", "name": "神奈川県産業人材育成支援事業", "max_amount": 300000,
     "target": "神奈川県内企業に勤める中小企業従業員",
     "description": "神奈川県が実施する産業人材育成のための補助制度。IT・AI・DX人材育成のための研修費用を支援。",
     "fields": "IT・AI・データ分析",
     "url": "https://www.pref.kanagawa.jp/"},
    {"prefecture": "愛知県", "name": "あいち人材育成基金（IT人材育成）", "max_amount": 200000,
     "target": "愛知県内在住・在勤の方",
     "description": "愛知県が実施するIT・DX人材育成支援。プログラミング・AI・クラウドなどの研修受講費用を一部補助。",
     "fields": "IT・AI",
     "url": "https://www.pref.aichi.jp/"},
    {"prefecture": "埼玉県", "name": "埼玉県スキルアップ支援事業（介護・福祉）", "max_amount": 200000,
     "target": "埼玉県内の介護・福祉分野の求職者・就業者",
     "description": "埼玉県が実施する介護・福祉分野の人材確保・育成支援。資格取得費用の一部を補助。",
     "fields": "介護・医療",
     "url": "https://www.pref.saitama.lg.jp/"},
    {"prefecture": "福岡県", "name": "福岡県ものづくり人材育成支援補助金", "max_amount": 300000,
     "target": "福岡県内のものづくり企業の従業員",
     "description": "福岡県が実施する製造業・ものづくり分野の人材育成支援。技能検定・専門資格取得費用を補助。",
     "fields": "IT・キャリア",
     "url": "https://www.pref.fukuoka.lg.jp/"},
    {"prefecture": "北海道", "name": "北海道産業人材確保・育成支援事業", "max_amount": 150000,
     "target": "北海道内の中小企業在籍の従業員",
     "description": "北海道の地域産業を支える人材育成を支援する補助事業。研修・資格取得費用の一部を補助。",
     "fields": "全分野",
     "url": "https://www.pref.hokkaido.lg.jp/"},
    {"prefecture": "兵庫県", "name": "兵庫県ものづくり産業人材育成支援事業", "max_amount": 200000,
     "target": "兵庫県内のものづくり分野の中小企業従業員",
     "description": "兵庫県が実施するものづくり・製造業分野の技術人材育成支援事業。",
     "fields": "IT・キャリア",
     "url": "https://www.pref.hyogo.lg.jp/"},
    {"prefecture": "京都府", "name": "京都府人材育成・スキルアップ支援補助金", "max_amount": 200000,
     "target": "京都府内在住・在勤の方",
     "description": "京都府が実施するスキルアップ・資格取得支援。IT・観光・伝統産業など幅広い分野で活用できる。",
     "fields": "全分野",
     "url": "https://www.pref.kyoto.jp/"},
]


# ─────────────────────────────────────────
# 方式7: ハロートレーニング
# ─────────────────────────────────────────
HELLO_TRAINING = [
    # 離職者向け
    {"name": "ITシステム開発科（Webアプリケーション開発）", "field": "IT", "target_type": "離職者向け", "duration": "6か月", "cost": "無料（テキスト代等実費）", "description": "JavaやPHP等を使ったWebアプリケーション開発技術を習得する訓練。ハローワーク経由で申し込み。", "url": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/koyou_roudou/jinzaikaihatsu/hellotraining_top.html"},
    {"name": "ネットワーク・クラウド技術科",               "field": "IT", "target_type": "離職者向け", "duration": "6か月", "cost": "無料", "description": "ネットワーク構築・クラウドサービス（AWS等）の実務スキルを習得する訓練。", "url": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/koyou_roudou/jinzaikaihatsu/hellotraining_top.html"},
    {"name": "Webデザイン・グラフィックデザイン科",         "field": "IT", "target_type": "離職者向け", "duration": "3か月", "cost": "無料", "description": "Photoshop・Illustrator・HTMLなどWebデザインの実務スキルを習得する訓練。", "url": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/koyou_roudou/jinzaikaihatsu/hellotraining_top.html"},
    {"name": "医療事務・調剤薬局事務科",                   "field": "医療","target_type": "離職者向け", "duration": "3か月", "cost": "無料", "description": "医療事務・調剤薬局事務のスキルを習得し、医療機関への就職を目指す訓練。", "url": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/koyou_roudou/jinzaikaihatsu/hellotraining_top.html"},
    {"name": "介護サービス科（初任者研修含む）",           "field": "介護","target_type": "離職者向け", "duration": "3か月", "cost": "無料", "description": "介護職員初任者研修を含む介護実務スキルを習得する訓練。修了後は介護施設への就職をサポート。", "url": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/koyou_roudou/jinzaikaihatsu/hellotraining_top.html"},
    {"name": "簿記・会計・税務科",                         "field": "会計","target_type": "離職者向け", "duration": "3か月", "cost": "無料", "description": "簿記2・3級の資格取得を目指す訓練。経理・会計事務の就職を目指す方向け。", "url": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/koyou_roudou/jinzaikaihatsu/hellotraining_top.html"},
    # 在職者向け
    {"name": "AI・データ分析基礎講座（在職者向け）",       "field": "AI", "target_type": "在職者向け", "duration": "2日〜5日", "cost": "有料（低廉）", "description": "在職者向けの短期IT研修。Python・機械学習・データ分析の基礎を学ぶ。就業しながら受講可能。", "url": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/koyou_roudou/jinzaikaihatsu/hellotraining_top.html"},
    {"name": "DXリスキリング講座（在職者向け）",           "field": "IT", "target_type": "在職者向け", "duration": "1か月〜3か月", "cost": "有料（低廉）", "description": "在職者向けのDX・デジタルスキル習得講座。クラウド・業務改善・RPAなどを学ぶ。", "url": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/koyou_roudou/jinzaikaihatsu/hellotraining_top.html"},
    # オンライン訓練
    {"name": "オンライン訓練（IT・プログラミング）",        "field": "IT", "target_type": "離職者向け", "duration": "3か月〜6か月", "cost": "無料", "description": "e-ラーニングで学べるハロートレーニングのオンライン訓練コース。プログラミング・Webデザイン・AI等。", "url": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/koyou_roudou/jinzaikaihatsu/hellotraining_top.html"},
    {"name": "オンライン訓練（語学・ビジネススキル）",      "field": "語学","target_type": "在職者向け", "duration": "1か月〜3か月", "cost": "有料（低廉）", "description": "e-ラーニングで学べる語学・ビジネススキル習得の訓練。英語・ビジネス文書・マーケティング等。", "url": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/koyou_roudou/jinzaikaihatsu/hellotraining_top.html"},
]


# ─────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────
def run_migrations(conn):
    for sql in MIGRATIONS:
        try:
            conn.execute(sql)
            print(f"  ✓ {sql[:60].strip()}...")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                pass  # すでに適用済み
            else:
                print(f"  ⚠ {e}")
    conn.commit()


def get_or_create_school(conn, name, data):
    row = conn.execute("SELECT id FROM schools WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    conn.execute("""INSERT INTO schools (name, url, category, description, source)
                    VALUES (?, ?, ?, ?, ?)""",
                 (name, data.get("url"), data.get("category", "その他"),
                  data.get("description"), data.get("source", "スクール公式サイト")))
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def parse_price_after(price, rate):
    if price is None: return None
    return round(price * (1 - rate / 100))


def insert_course_if_new(conn, school_id, c):
    exists = conn.execute(
        "SELECT 1 FROM courses WHERE school_id=? AND name=?",
        (school_id, c["name"])
    ).fetchone()
    if exists:
        return False

    price = c.get("price")
    rate  = c.get("benefit_rate", 20)
    pab   = c.get("price_after_benefit") or parse_price_after(price, rate)

    dur = c.get("duration")
    dur_months = None
    if dur:
        m = re.search(r"(\d+(?:\.\d+)?)か月", dur)
        if m:
            dur_months = float(m.group(1))

    conn.execute("""
        INSERT INTO courses
            (school_id, name, field, benefit_type, benefit_rate,
             price, price_after_benefit, duration, duration_months,
             format, prefecture, target_qualification, course_url,
             notes, source, source_url, course_number)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        school_id,
        c.get("name"),
        c.get("field", "キャリア"),
        c.get("benefit_type", "一般"),
        rate,
        price,
        pab,
        dur,
        dur_months,
        c.get("format", "通学"),
        c.get("prefecture", "全国"),
        c.get("target_qualification"),
        c.get("course_url"),
        c.get("notes"),
        c.get("source", "スクール公式サイト"),
        c.get("source_url"),
        c.get("course_number"),
    ))
    return True


def seed_pdf_data(conn):
    """方式1・5: 厚労省PDFデータの投入"""
    if not JSON_PATH.exists():
        print(f"  ⚠ {JSON_PATH} が見つかりません。スキップ。")
        return 0

    with open(JSON_PATH, encoding="utf-8") as f:
        pdf_courses = json.load(f)

    school_cache = {}
    added = 0

    for c in pdf_courses:
        sname = c["school_name"]
        if sname not in school_cache:
            school_cache[sname] = get_or_create_school(conn, sname, {
                "category": "医療介護" if c["field"] in ("医療", "介護") else "その他",
                "source": "厚労省プレスリリース",
            })
        sid = school_cache[sname]

        record = {
            "name":             c["course_name"],
            "field":            c["field"],
            "benefit_type":     c["benefit_type"],
            "benefit_rate":     c["benefit_rate"],
            "price":            None,
            "price_after_benefit": None,
            "duration":         c.get("duration"),
            "format":           c.get("format", "通学"),
            "prefecture":       c.get("prefecture", ""),
            "target_qualification": c.get("target_qualification"),
            "course_number":    c.get("course_number"),
            "source":           "厚労省プレスリリース（令和8年4月1日付け）",
            "source_url":       "https://www.mhlw.go.jp/stf/newpage_70323.html",
        }
        if insert_course_if_new(conn, sid, record):
            added += 1

    conn.commit()
    print(f"  ✓ 厚労省PDFデータ: {added}件 追加")
    return added


def seed_manual_data(conn):
    """方式2・4・6: 主要スクール手動データ"""
    school_map = {s["name"]: s for s in MANUAL_SCHOOLS}
    added = 0

    for c in MANUAL_COURSES:
        sname = c["school"]
        sdata = school_map.get(sname, {"category": "その他", "source": "スクール公式サイト"})
        sid = get_or_create_school(conn, sname, sdata)

        record = {
            "name":             c["name"],
            "field":            c["field"],
            "benefit_type":     c["benefit_type"],
            "benefit_rate":     c["benefit_rate"],
            "price":            c.get("price"),
            "duration":         c.get("duration"),
            "format":           c.get("format", "通学"),
            "prefecture":       c.get("prefecture", "全国"),
            "target_qualification": c.get("target_qualification"),
            "source":           "スクール公式サイト",
        }
        if insert_course_if_new(conn, sid, record):
            added += 1

    conn.commit()
    print(f"  ✓ 手動スクールデータ: {added}件 追加")
    return added


def seed_qualifications(conn):
    """方式3: 資格マスターデータ"""
    added = 0
    for q in QUALIFICATIONS:
        exists = conn.execute("SELECT 1 FROM qualifications WHERE name=?", (q["name"],)).fetchone()
        if exists:
            continue
        conn.execute("""
            INSERT INTO qualifications
                (name, name_kana, field, category_slug, qual_type,
                 difficulty, pass_rate, exam_fee, exam_schedule, official_url, description)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (q["name"], q.get("name_kana"), q["field"], q["category_slug"],
              q.get("qual_type"), q.get("difficulty"), q.get("pass_rate"),
              q.get("exam_fee"), q.get("exam_schedule"), q.get("official_url"),
              q.get("description")))
        added += 1
    conn.commit()
    print(f"  ✓ 資格マスター: {added}件 追加")
    return added


def seed_local_benefits(conn):
    """方式8: 自治体給付金データ"""
    added = 0
    for lb in LOCAL_BENEFITS:
        exists = conn.execute(
            "SELECT 1 FROM local_benefits WHERE prefecture=? AND name=?",
            (lb["prefecture"], lb["name"])
        ).fetchone()
        if exists:
            continue
        conn.execute("""
            INSERT INTO local_benefits (prefecture, name, description, max_amount, target, fields, url)
            VALUES (?,?,?,?,?,?,?)
        """, (lb["prefecture"], lb["name"], lb.get("description"),
              lb.get("max_amount"), lb.get("target"), lb.get("fields"), lb.get("url")))
        added += 1
    conn.commit()
    print(f"  ✓ 自治体給付金: {added}件 追加")
    return added


def seed_hello_training(conn):
    """方式7: ハロートレーニングデータ"""
    added = 0
    for ht in HELLO_TRAINING:
        exists = conn.execute("SELECT 1 FROM hello_training WHERE name=?", (ht["name"],)).fetchone()
        if exists:
            continue
        conn.execute("""
            INSERT INTO hello_training (name, field, target_type, duration, cost, description, url)
            VALUES (?,?,?,?,?,?,?)
        """, (ht["name"], ht.get("field"), ht.get("target_type"),
              ht.get("duration"), ht.get("cost"), ht.get("description"), ht.get("url")))
        added += 1
    conn.commit()
    print(f"  ✓ ハロートレーニング: {added}件 追加")
    return added


def update_existing_source(conn):
    """既存データにsource='スクール公式サイト'を設定"""
    conn.execute("UPDATE courses SET source='スクール公式サイト' WHERE source IS NULL")
    conn.execute("UPDATE schools SET source='スクール公式サイト' WHERE source IS NULL")
    conn.commit()


def print_stats(conn):
    print("\n" + "="*55)
    print("  📊 統計サマリー")
    print("="*55)

    total_c = conn.execute("SELECT COUNT(*) FROM courses WHERE is_active=1").fetchone()[0]
    total_s = conn.execute("SELECT COUNT(*) FROM schools").fetchone()[0]
    total_q = conn.execute("SELECT COUNT(*) FROM qualifications").fetchone()[0]
    total_lb = conn.execute("SELECT COUNT(*) FROM local_benefits").fetchone()[0]
    total_ht = conn.execute("SELECT COUNT(*) FROM hello_training").fetchone()[0]

    print(f"  総講座数:          {total_c:>5} 件")
    print(f"  総スクール数:      {total_s:>5} 校")
    print(f"  総資格数:          {total_q:>5} 件")
    print(f"  自治体給付金:      {total_lb:>5} 件")
    print(f"  ハロートレーニング:{total_ht:>5} 件")

    print("\n  ─ カテゴリ別講座数 ─")
    rows = conn.execute("""
        SELECT field, COUNT(*) n FROM courses WHERE is_active=1 GROUP BY field ORDER BY n DESC
    """).fetchall()
    for r in rows:
        print(f"    {r[0] or '(未分類)':<12}: {r[1]:>4} 件")

    print("\n  ─ 給付金種別 ─")
    rows = conn.execute("""
        SELECT benefit_type, COUNT(*) n FROM courses WHERE is_active=1
        GROUP BY benefit_type ORDER BY n DESC
    """).fetchall()
    for r in rows:
        print(f"    {r[0]:<10}: {r[1]:>4} 件")

    print("\n  ─ データソース別 ─")
    rows = conn.execute("""
        SELECT source, COUNT(*) n FROM courses WHERE is_active=1
        GROUP BY source ORDER BY n DESC
    """).fetchall()
    for r in rows:
        src = (r[0] or '不明')[:35]
        print(f"    {src:<35}: {r[1]:>4} 件")

    print("\n  ─ 都道府県 TOP10 ─")
    rows = conn.execute("""
        SELECT prefecture, COUNT(*) n FROM courses WHERE is_active=1
        GROUP BY prefecture ORDER BY n DESC LIMIT 10
    """).fetchall()
    for r in rows:
        print(f"    {(r[0] or '全国'):<10}: {r[1]:>4} 件")
    print("="*55)


def main():
    if not DB_PATH.exists():
        print(f"[ERROR] {DB_PATH} が見つかりません。先に fetch_courses.py を実行してください。")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("🚀 拡張データ投入開始\n")

    print("【1】スキーマ拡張...")
    run_migrations(conn)

    print("【2】既存データ更新...")
    update_existing_source(conn)

    print("【3】厚労省PDFデータ（方式1・5）...")
    seed_pdf_data(conn)

    print("【4】主要スクールデータ（方式2・4・6）...")
    seed_manual_data(conn)

    print("【5】資格マスターデータ（方式3）...")
    seed_qualifications(conn)

    print("【6】自治体給付金データ（方式8）...")
    seed_local_benefits(conn)

    print("【7】ハロートレーニングデータ（方式7）...")
    seed_hello_training(conn)

    print_stats(conn)
    conn.close()
    print("\n✅ 完了！")


if __name__ == "__main__":
    main()
