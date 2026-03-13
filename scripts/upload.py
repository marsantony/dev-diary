"""推送摘要資料到 Cloudflare KV。"""

import json
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
KV_BINDING = "DEV_DIARY_KV"


def kv_get(key: str) -> str | None:
    """從 Cloudflare KV 讀取。回傳值或 None。"""
    result = subprocess.run(
        [
            "wrangler",
            "kv",
            "key",
            "get",
            f"--binding={KV_BINDING}",
            key,
            "--remote",
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def kv_put(key: str, value: str) -> bool:
    """寫入 Cloudflare KV。回傳是否成功。"""
    result = subprocess.run(
        [
            "wrangler",
            "kv",
            "key",
            "put",
            f"--binding={KV_BINDING}",
            key,
            value,
            "--remote",
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
    )
    if result.returncode != 0:
        print(f"  [ERROR] KV put failed for {key}: {result.stderr[:200]}")
        return False
    print(f"  [KV] {key} uploaded")
    return True


def upload_all(
    daily_public: list[dict],
    daily_private: list[dict],
    weekly_public: list[dict],
    weekly_private: list[dict],
    session_dates: dict | None = None,
    existing_meta: dict | None = None,
) -> bool:
    """上傳所有摘要到 Cloudflare。回傳是否全部成功。"""
    if not daily_public and not daily_private and not weekly_public:
        print("No data to upload.")
        return True

    print("\nUploading to Cloudflare KV...")

    # 上傳每日摘要
    for pub in daily_public:
        date = pub["date"]
        kv_put(f"public:daily:{date}", json.dumps(pub, ensure_ascii=False))

    for priv in daily_private:
        date = priv["date"]
        kv_put(f"private:daily:{date}", json.dumps(priv, ensure_ascii=False))

    # 上傳週報
    for wp in weekly_public:
        date = wp.get("weekEnd", "")
        if date:
            kv_put(f"public:weekly:{date}", json.dumps(wp, ensure_ascii=False))

    for wp in weekly_private:
        date = wp.get("weekEnd", "")
        if date:
            kv_put(f"private:weekly:{date}", json.dumps(wp, ensure_ascii=False))

    # 更新 meta:latest（含完整索引，前端從 API 讀取）
    if existing_meta is None:
        raw = kv_get("meta:latest")
        existing_meta = json.loads(raw) if raw else {}
    meta_base = existing_meta or {}
    existing_dates = meta_base.get("dates", [])
    existing_weekly = meta_base.get("weeklyDates", [])
    existing_session_dates = meta_base.get("sessionDates", {})

    new_dates = [d["date"] for d in daily_public]
    all_dates = sorted(set(existing_dates + new_dates), reverse=True)

    new_weekly_dates = [wp.get("weekEnd") for wp in weekly_public if wp.get("weekEnd")]
    weekly_dates = sorted(set(existing_weekly + new_weekly_dates), reverse=True)
    if session_dates:
        existing_session_dates.update(session_dates)

    meta = {
        "lastDaily": all_dates[0] if all_dates else None,
        "lastWeekly": weekly_dates[0] if weekly_dates else None,
        "dates": all_dates,
        "weeklyDates": weekly_dates,
        "sessionDates": existing_session_dates,
    }
    kv_put("meta:latest", json.dumps(meta, ensure_ascii=False))
    print(f"  [KV] meta:latest updated ({len(all_dates)} dates)")

    return True
