#!/usr/bin/env python3
"""
記事自動生成スクリプト

使い方:
    python generators/gen_article.py              # キーワードを自動選択して1記事生成
    python generators/gen_article.py --id 5       # キーワードIDを指定
    python generators/gen_article.py --dry-run    # API呼び出しなしで動作確認

環境変数:
    ANTHROPIC_API_KEY  Anthropic APIキー（必須）
"""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

# Windows環境でのUTF-8出力を強制
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import anthropic
except ImportError:
    print("[ERROR] anthropicパッケージが見つかりません。pip install anthropic を実行してください。")
    sys.exit(1)

try:
    from slugify import slugify
except ImportError:
    def slugify(text, **kwargs):
        # フォールバック: 英数字とハイフンのみ残す
        return re.sub(r"[^a-z0-9-]", "-", text.lower()).strip("-")

ROOT         = Path(__file__).parent.parent
KEYWORDS_PATH = ROOT / "generators" / "keywords.json"
ARTICLES_DIR  = ROOT / "articles"
MODEL         = "claude-sonnet-4-20250514"

# カテゴリ → アイコンのマッピング
CATEGORY_ICON = {
    "給付金":   "💡",
    "IT":       "💻",
    "不動産":   "🏠",
    "法務":     "⚖️",
    "会計":     "📊",
    "医療介護": "🏥",
    "語学":     "🌍",
}


def load_keywords() -> list[dict]:
    with KEYWORDS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def get_written_keyword_ids() -> set[int]:
    """articles/ 内のマークダウンファイルからkeyword_idを収集"""
    written = set()
    if not ARTICLES_DIR.exists():
        return written
    for md_file in ARTICLES_DIR.glob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        m = re.search(r"^keyword_id:\s*(\d+)", text, re.MULTILINE)
        if m:
            written.add(int(m.group(1)))
    return written


def pick_keyword(keywords: list[dict], force_id: int | None = None) -> dict | None:
    """未執筆のキーワードを優先度順に選択"""
    if force_id is not None:
        for kw in keywords:
            if kw["id"] == force_id:
                return kw
        print(f"[ERROR] keyword_id={force_id} が見つかりません")
        return None

    written = get_written_keyword_ids()
    candidates = [kw for kw in keywords if kw["id"] not in written]
    if not candidates:
        print("[INFO] すべてのキーワードが執筆済みです")
        return None

    # priority 昇順（1が最高）でソート、同priority内はidの小さい順
    candidates.sort(key=lambda k: (k["priority"], k["id"]))
    return candidates[0]


def build_prompt(keyword: dict) -> str:
    return f"""あなたは教育訓練給付金と資格取得に精通したSEOライターです。
以下のキーワードで、資格バンク（https://shikaku-bank.com）向けの記事を書いてください。

## キーワード
{keyword["keyword"]}

## 記事要件
- 文体: です・ます調
- 文字数: 本文1,500〜2,500文字
- タイトル: 30〜60文字（クリックされやすい具体的な表現）
- meta description: 80〜120文字（検索結果でユーザーを引き付ける内容）
- H2見出し: 3〜6個
- 内部リンク: 最低3本（下記リンクを本文中に自然に組み込む）
  - [給付金対象講座を検索する](/search/)
  - [IT・プログラミング講座一覧](/category/it/)
  - [会計・簿記講座一覧](/category/accounting/)
  - [不動産・宅建講座一覧](/category/estate/)
  - [医療・介護講座一覧](/category/medical/)
  - [法務・行政講座一覧](/category/legal/)
  - [給付金とは](/about-kyufu/)
- 読者: 資格取得・スキルアップを検討している社会人
- トーン: 中立・親しみやすい・具体的な数字や事例を含む

## 出力形式
必ず以下のYAMLフロントマターで始まるMarkdownで出力してください。
コードブロック（```）で囲まず、そのままMarkdownを出力してください。

---
title: （タイトル）
slug: （英数字とハイフンのみ・記事内容を端的に表す）
category: （IT / 給付金 / 不動産 / 法務 / 会計 / 医療介護 / 語学 のいずれか）
keyword_id: {keyword["id"]}
published_at: {date.today().isoformat()}
excerpt: （meta descriptionと同じ内容・80〜120文字）
icon: （カテゴリに合った絵文字1つ）
---

（本文）
"""


def generate_article(keyword: dict, dry_run: bool = False) -> str:
    """Claude APIを呼び出して記事を生成する"""
    prompt = build_prompt(keyword)

    if dry_run:
        print("[dry-run] API呼び出しをスキップします")
        return f"""---
title: 【テスト】{keyword["keyword"]}の完全ガイド
slug: test-{keyword["id"]}
category: 給付金
keyword_id: {keyword["id"]}
published_at: {date.today().isoformat()}
excerpt: これはdry-runで生成されたテスト記事です。実際の記事はAnthropicAPIで生成されます。
icon: 📝
---

## テスト記事

これはdry-runモードで生成されたテスト記事です。

実際の生成時は[給付金対象講座を検索する](/search/)から講座を探せます。
"""

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[ERROR] 環境変数 ANTHROPIC_API_KEY が設定されていません")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    print(f"[API] Claude ({MODEL}) に記事生成をリクエスト中...")
    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def save_article(content: str) -> Path:
    """フロントマターからslugを取得してarticles/{slug}.mdに保存"""
    # slugをフロントマターから抽出
    m = re.search(r"^slug:\s*(.+)$", content, re.MULTILINE)
    if not m:
        # フォールバック: 日付ベースのファイル名
        slug = f"article-{date.today().isoformat()}"
    else:
        slug = m.group(1).strip()

    ARTICLES_DIR.mkdir(exist_ok=True)
    out_path = ARTICLES_DIR / f"{slug}.md"

    # 同名ファイルが存在する場合は連番を付与
    if out_path.exists():
        i = 2
        while (ARTICLES_DIR / f"{slug}-{i}.md").exists():
            i += 1
        out_path = ARTICLES_DIR / f"{slug}-{i}.md"

    out_path.write_text(content, encoding="utf-8")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="資格バンク 記事自動生成")
    parser.add_argument("--id",      type=int, help="生成するキーワードのID")
    parser.add_argument("--dry-run", action="store_true", help="API呼び出しなしで動作確認")
    args = parser.parse_args()

    keywords = load_keywords()
    keyword  = pick_keyword(keywords, force_id=args.id)

    if keyword is None:
        sys.exit(0)

    print(f"[keyword] id={keyword['id']} / {keyword['keyword']} / category={keyword['category']}")

    content  = generate_article(keyword, dry_run=args.dry_run)
    out_path = save_article(content)

    print(f"[saved]  {out_path.relative_to(ROOT)}")
    print(f"\n✅ 記事生成完了")


if __name__ == "__main__":
    main()
