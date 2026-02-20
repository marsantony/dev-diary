"""從 Claude Code session .jsonl 檔案中提取結構化資料。"""

import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

SESSION_DIR = Path.home() / ".claude" / "projects" / "-home-mars-claudeshare"
TZ_TPE = timezone(timedelta(hours=8))

# 要過濾掉的系統標籤 pattern
SYSTEM_TAG_PATTERNS = [
    re.compile(r"<ide_opened_file>.*?</ide_opened_file>", re.DOTALL),
    re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL),
    re.compile(r"<ide_selection>.*?</ide_selection>", re.DOTALL),
]


def clean_text(text: str) -> str:
    """移除系統標籤，只保留使用者實際輸入的文字。"""
    for pattern in SYSTEM_TAG_PATTERNS:
        text = pattern.sub("", text)
    return text.strip()


def extract_session(filepath: Path) -> dict | None:
    """從單一 .jsonl 檔案提取 session 摘要資料。"""
    user_messages = []
    tools_used = []
    files_edited = set()
    git_operations = []
    session_id = filepath.stem[:8]
    first_timestamp = None
    message_count = 0

    with open(filepath) as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = obj.get("type")

            # 取得 session 時間
            if first_timestamp is None and obj.get("timestamp"):
                first_timestamp = obj["timestamp"]

            # 提取 user 訊息
            if msg_type == "user":
                message_count += 1
                msg = obj.get("message", {})
                content = msg.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            cleaned = clean_text(item["text"])
                            if cleaned:
                                user_messages.append(cleaned[:500])

            # 提取 tool 使用紀錄
            elif msg_type == "assistant":
                msg = obj.get("message", {})
                content = msg.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_use":
                            tool_name = item.get("name", "")
                            tool_input = item.get("input", {})

                            tools_used.append(tool_name)

                            # 追蹤檔案編輯
                            if tool_name in ("Edit", "Write"):
                                fp = tool_input.get("file_path", "")
                                if fp:
                                    files_edited.add(fp)

                            # 追蹤 git 操作
                            if tool_name == "Bash":
                                cmd = tool_input.get("command", "")
                                if any(
                                    kw in cmd
                                    for kw in [
                                        "git commit",
                                        "git push",
                                        "git init",
                                        "gh repo create",
                                        "gh pr create",
                                    ]
                                ):
                                    git_operations.append(cmd[:200])

    # 過濾無實質內容的 session（只有系統訊息、無 user 訊息）
    if not user_messages:
        return None

    # 解析時間
    time_str = ""
    if first_timestamp:
        try:
            dt = datetime.fromisoformat(first_timestamp.replace("Z", "+00:00"))
            dt_local = dt.astimezone(TZ_TPE)
            time_str = dt_local.strftime("%H:%M")
        except (ValueError, TypeError):
            pass

    return {
        "id": session_id,
        "time": time_str,
        "message_count": message_count,
        "user_messages": user_messages[:20],  # 最多 20 則
        "tools_used": list(set(tools_used)),
        "files_edited": sorted(files_edited),
        "git_operations": git_operations,
    }


def _get_session_date(filepath: Path) -> str | None:
    """取得 session 的日期（台灣時間），優先用第一筆 timestamp，fallback 用 mtime。"""
    try:
        with open(filepath) as f:
            for line in f:
                obj = json.loads(line)
                ts = obj.get("timestamp")
                if ts:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(TZ_TPE)
                    return dt.strftime("%Y-%m-%d")
    except (json.JSONDecodeError, OSError):
        pass
    # fallback: 用 mtime
    mtime = datetime.fromtimestamp(filepath.stat().st_mtime, tz=TZ_TPE)
    return mtime.strftime("%Y-%m-%d")


def extract_sessions_for_date(target_date: datetime) -> list[dict]:
    """提取指定日期（台灣時間）的所有 session 資料。"""
    sessions = []

    if not SESSION_DIR.exists():
        return sessions

    target_date_str = target_date.strftime("%Y-%m-%d")

    for filepath in SESSION_DIR.glob("*.jsonl"):
        session_date = _get_session_date(filepath)
        if session_date != target_date_str:
            continue

        session = extract_session(filepath)
        if session:
            sessions.append(session)

    # 按時間排序
    sessions.sort(key=lambda s: s["time"])
    return sessions


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        date = datetime.strptime(sys.argv[1], "%Y-%m-%d").replace(tzinfo=TZ_TPE)
    else:
        date = datetime.now(TZ_TPE)

    sessions = extract_sessions_for_date(date)
    print(json.dumps(sessions, ensure_ascii=False, indent=2))
