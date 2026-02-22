"""主腳本：從 session 資料產生每日摘要和週報，推送到 Cloudflare。"""

import json
import os
import re
import subprocess
import sys
import traceback
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract import extract_sessions_for_date

TZ_TPE = timezone(timedelta(hours=8))
PROJECT_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DATA_DIR = PROJECT_DIR / "public" / "data"
DISCORD_WEBHOOK_URL = os.environ.get("DEV_DIARY_DISCORD_WEBHOOK", "")


def notify_discord(message: str):
    """發送 Discord webhook 通知。"""
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        data = json.dumps({"content": message}).encode()
        req = urllib.request.Request(
            DISCORD_WEBHOOK_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "dev-diary-bot",
            },
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"  [WARN] Discord notification failed: {e}")

SYSTEM_PROMPT_PUBLIC = """\
你是一個開發日誌產生器。根據提供的 Claude Code 對話 session 資料，產生「公開版」每日摘要。

規則：
- 使用繁體中文
- 只寫「做了什麼」，不寫「怎麼做」
- 不暴露：實作細節、架構設計、安全機制、速率限制、API URL、檔案路徑
- 每個 session 一句話摘要
- 當日彙整 2-3 句，每句用換行（\\n）分隔
- 如果 session 的 user_messages 太少或內容是純問答/閒聊，摘要可以很短

輸出 JSON 格式：
{
  "sessions": [
    {"id": "session_id", "time": "HH:MM", "summary": "一句話摘要"}
  ],
  "daySummary": "第一句彙整\\n第二句彙整\\n第三句彙整"
}
"""

SYSTEM_PROMPT_PRIVATE = """\
你是一個開發日誌產生器。根據提供的 Claude Code 對話 session 資料，產生「完整版」每日摘要。

規則：
- 使用繁體中文
- 包含技術細節：修改了哪些檔案、用了什麼工具、架構決策
- 包含 git 操作（commit、push、repo 建立等）
- 每個 session 2-4 句詳細摘要，每句用換行（\\n）分隔
- 當日彙整也用換行分隔重點
- 最後一段是當日彙整（含技術重點）

輸出 JSON 格式：
{
  "sessions": [
    {"id": "session_id", "time": "HH:MM", "summary": "簡短標題", "details": "第一句摘要\\n第二句摘要\\n第三句摘要"}
  ],
  "daySummary": "當日彙整（簡潔版）",
  "dayDetails": "技術重點一\\n技術重點二\\n技術重點三"
}
"""

SYSTEM_PROMPT_WEEKLY_PUBLIC = """\
你是一個開發週報產生器。根據提供的每日摘要資料，產生「公開版」週報。

規則：
- 使用繁體中文
- 只寫「做了什麼」，不寫「怎麼做」
- 不暴露實作細節、架構、安全機制
- 分類整理：新建專案、修復與強化、基礎建設、學習研究
- 簡潔有力

輸出 JSON 格式：
{
  "weekStart": "YYYY-MM-DD",
  "weekEnd": "YYYY-MM-DD",
  "summary": "週報彙整（markdown 格式）"
}
"""

SYSTEM_PROMPT_WEEKLY_PRIVATE = """\
你是一個開發週報產生器。根據提供的每日摘要資料，產生「完整版」週報。

規則：
- 使用繁體中文
- 包含所有技術細節
- 分類整理：新建專案、修復與強化、基礎建設、規範更新、學習研究
- 列出待辦事項

輸出 JSON 格式：
{
  "weekStart": "YYYY-MM-DD",
  "weekEnd": "YYYY-MM-DD",
  "summary": "週報彙整（markdown 格式）",
  "details": "完整技術週報（markdown 格式）"
}
"""


def call_claude(system_prompt: str, user_content: str) -> str:
    """呼叫 claude --print CLI 產生摘要（使用 Claude 訂閱，不需 API key）。"""
    env = os.environ.copy()
    # 移除 CLAUDECODE 環境變數，避免 CLI 拒絕在另一個 Claude Code session 內執行
    env.pop("CLAUDECODE", None)

    try:
        result = subprocess.run(
            ["claude", "--print", "--system-prompt", system_prompt],
            input=user_content,
            capture_output=True,
            text=True,
            env=env,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("claude CLI timed out after 300s")
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI failed: {result.stderr.strip()}")
    return extract_json(result.stdout.strip())


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def extract_json(text: str) -> str:
    """從 Claude 回傳的文字中提取 JSON 字串（可能被 markdown code block 包裹）。"""
    # 嘗試直接 parse
    stripped = text.strip()
    if stripped.startswith("{"):
        # 可能後面有多餘文字，找到配對的 } 為止
        try:
            json.loads(stripped)
            return stripped
        except json.JSONDecodeError:
            pass

    # 從 ```json ... ``` code block 中提取
    match = _JSON_BLOCK_RE.search(text)
    if match:
        return match.group(1).strip()

    # 最後嘗試找第一個 { 到最後一個 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    return text


def get_last_generated_date() -> str | None:
    """從本地 meta 檔取得上次產生的日期。"""
    meta_file = PROJECT_DIR / "scripts" / ".meta.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
        return meta.get("lastDaily")
    return None


def save_meta(last_daily: str, last_weekly: str | None = None):
    """更新本地 meta 檔。"""
    meta_file = PROJECT_DIR / "scripts" / ".meta.json"
    meta = {}
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
    meta["lastDaily"] = last_daily
    if last_weekly:
        meta["lastWeekly"] = last_weekly
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2))


def generate_daily(target_date: datetime) -> tuple[dict | None, dict | None, dict]:
    """產生指定日期的公開版和完整版摘要。回傳 (public, private, session_dates_map)。"""
    sessions = extract_sessions_for_date(target_date)
    if not sessions:
        return None, None, {}

    date_str = target_date.strftime("%Y-%m-%d")
    print(f"  [{date_str}] {len(sessions)} sessions found, generating summaries...")

    # 收集跨日 session 資訊：{session_id: [dates]}
    session_dates_map = {}
    for s in sessions:
        if len(s.get("all_dates", [])) > 1:
            session_dates_map[s["id"]] = s["all_dates"]

    # 準備輸入資料
    session_data = json.dumps(sessions, ensure_ascii=False, indent=2)
    user_content = f"日期：{date_str}\n\nSession 資料：\n{session_data}"

    # 產生公開版
    try:
        public_raw = call_claude(SYSTEM_PROMPT_PUBLIC, user_content)
        public = json.loads(public_raw)
        public["date"] = date_str
    except (json.JSONDecodeError, RuntimeError) as e:
        print(f"  [WARN] Public summary failed: {e}")
        public = None

    # 產生完整版
    try:
        private_raw = call_claude(SYSTEM_PROMPT_PRIVATE, user_content)
        private = json.loads(private_raw)
        private["date"] = date_str
    except (json.JSONDecodeError, RuntimeError) as e:
        print(f"  [WARN] Private summary failed: {e}")
        private = None

    return public, private, session_dates_map


def load_daily_summaries(
    week_start: datetime, week_end: datetime
) -> tuple[list[dict], list[dict]]:
    """從磁碟讀公開版、從 KV 讀私密版每日摘要。"""
    from upload import kv_get

    public_list: list[dict] = []
    private_list: list[dict] = []
    current = week_start
    while current <= week_end:
        date_str = current.strftime("%Y-%m-%d")
        # 公開版：從磁碟讀
        pub_file = PUBLIC_DATA_DIR / f"daily-{date_str}.json"
        if pub_file.exists():
            public_list.append(json.loads(pub_file.read_text()))
        # 私密版：從 KV 讀
        priv_data = kv_get(f"private:daily:{date_str}")
        if priv_data:
            try:
                private_list.append(json.loads(priv_data))
            except json.JSONDecodeError:
                print(f"  [WARN] Failed to parse private daily for {date_str}")
        current += timedelta(days=1)
    return public_list, private_list


def generate_weekly(
    week_start: datetime,
    week_end: datetime,
    daily_public: list[dict],
    daily_private: list[dict],
) -> tuple[dict | None, dict | None]:
    """產生週報。"""
    if not daily_public and not daily_private:
        return None, None

    print(
        f"  Generating weekly report: {week_start.strftime('%Y-%m-%d')} ~ {week_end.strftime('%Y-%m-%d')}..."
    )

    ws = week_start.strftime("%Y-%m-%d")
    we = week_end.strftime("%Y-%m-%d")

    # 公開版週報
    public_input = json.dumps(daily_public, ensure_ascii=False, indent=2)
    try:
        public_raw = call_claude(SYSTEM_PROMPT_WEEKLY_PUBLIC, public_input)
        public = json.loads(public_raw)
        # 強制使用正確的日期範圍（不依賴 Claude 回傳的值）
        public["weekStart"] = ws
        public["weekEnd"] = we
    except (json.JSONDecodeError, RuntimeError) as e:
        print(f"  [WARN] Weekly public failed: {e}")
        public = None

    # 完整版週報
    private_input = json.dumps(daily_private, ensure_ascii=False, indent=2)
    try:
        private_raw = call_claude(SYSTEM_PROMPT_WEEKLY_PRIVATE, private_input)
        private = json.loads(private_raw)
        private["weekStart"] = ws
        private["weekEnd"] = we
    except (json.JSONDecodeError, RuntimeError) as e:
        print(f"  [WARN] Weekly private failed: {e}")
        private = None

    return public, private


def main():
    today = datetime.now(TZ_TPE).replace(hour=0, minute=0, second=0, microsecond=0)

    # 判斷要處理哪些日期
    last_date_str = get_last_generated_date()
    if last_date_str:
        last_date = datetime.strptime(last_date_str, "%Y-%m-%d").replace(tzinfo=TZ_TPE)
        start_date = last_date + timedelta(days=1)
    else:
        # 首次執行，只處理今天
        start_date = today

    # === 每日摘要生成 ===
    all_public = []
    all_private = []
    all_session_dates = {}  # {session_id: [dates]}
    last_processed = None

    if start_date <= today:
        dates_to_process = []
        current = start_date
        while current <= today:
            dates_to_process.append(current)
            current += timedelta(days=1)

        print(f"Processing {len(dates_to_process)} date(s): {dates_to_process[0].strftime('%Y-%m-%d')} ~ {today.strftime('%Y-%m-%d')}")

        for date in dates_to_process:
            date_str = date.strftime("%Y-%m-%d")

            # 已存在就跳過，不重複生成
            pub_file = PUBLIC_DATA_DIR / f"daily-{date_str}.json"
            if pub_file.exists():
                print(f"  [{date_str}] already exists, skipping.")
                last_processed = date_str
                continue

            public, private, session_dates_map = generate_daily(date)
            if public:
                all_public.append(public)
                PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
                out_file = PUBLIC_DATA_DIR / f"daily-{date_str}.json"
                out_file.write_text(json.dumps(public, ensure_ascii=False, indent=2))
            if private:
                all_private.append(private)
            for sid, dates in session_dates_map.items():
                all_session_dates[sid] = dates
            if public or private:
                last_processed = date_str
    else:
        print("No new dates to process.")

    # === 週報生成（獨立於每日生成，掃描已有的每日資料找漏掉的週報） ===
    weekly_public = None
    weekly_private = None

    # 從 index.json 取得所有已有每日摘要的日期，找出需要產生週報的週六
    index_file = PUBLIC_DATA_DIR / "index.json"
    if index_file.exists():
        index_data = json.loads(index_file.read_text())
        all_daily_dates = sorted(index_data.get("dates", []))
        if all_daily_dates:
            first_date = datetime.strptime(all_daily_dates[0], "%Y-%m-%d").replace(tzinfo=TZ_TPE)
            # 從第一筆每日摘要掃描到今天，找所有週六
            scan = first_date
            while scan <= today:
                if scan.weekday() == 5:  # 週六
                    week_end = scan
                    week_start = scan - timedelta(days=6)
                    we_str = week_end.strftime("%Y-%m-%d")

                    # 已有週報就跳過
                    if (PUBLIC_DATA_DIR / f"weekly-{we_str}.json").exists():
                        scan += timedelta(days=1)
                        continue

                    # 從磁碟/KV 讀回整週的每日摘要
                    week_pub, week_priv = load_daily_summaries(week_start, week_end)
                    if not week_pub and not week_priv:
                        scan += timedelta(days=1)
                        continue

                    print(f"  Generating missing weekly report for {we_str}...")
                    try:
                        weekly_public, weekly_private = generate_weekly(week_start, week_end, week_pub, week_priv)
                    except RuntimeError as e:
                        print(f"  [WARN] Weekly report generation failed: {e}")
                        weekly_public, weekly_private = None, None

                    if weekly_public:
                        out_file = PUBLIC_DATA_DIR / f"weekly-{we_str}.json"
                        out_file.write_text(json.dumps(weekly_public, ensure_ascii=False, indent=2))

                scan += timedelta(days=1)

    # === 上傳到 Cloudflare ===
    from upload import upload_all
    success = upload_all(all_public, all_private, weekly_public, weekly_private, all_session_dates)

    if success and last_processed:
        weekly_date = None
        if weekly_public:
            weekly_date = weekly_public.get("weekEnd")
        save_meta(last_processed, weekly_date)

    print(f"\nDone! Processed {len(all_public)} daily summaries.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        error_msg = traceback.format_exc()
        print(f"[FATAL] {error_msg}")
        notify_discord(f"❌ **dev-diary generate.py 失敗**\n```\n{error_msg[:1500]}\n```")
        sys.exit(1)
