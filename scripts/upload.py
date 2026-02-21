"""推送摘要資料到 Cloudflare KV 和靜態頁面。"""

import json
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
KV_BINDING = "DEV_DIARY_KV"


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
    weekly_public: dict | None,
    weekly_private: dict | None,
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
    if weekly_public:
        date = weekly_public.get("weekEnd", "")
        if date:
            kv_put(f"public:weekly:{date}", json.dumps(weekly_public, ensure_ascii=False))

    if weekly_private:
        date = weekly_private.get("weekEnd", "")
        if date:
            kv_put(f"private:weekly:{date}", json.dumps(weekly_private, ensure_ascii=False))

    # 更新 meta:latest
    meta = {
        "lastDaily": daily_public[-1]["date"] if daily_public else None,
        "lastWeekly": weekly_public.get("weekEnd") if weekly_public else None,
        "dates": [d["date"] for d in daily_public],
    }
    kv_put("meta:latest", json.dumps(meta, ensure_ascii=False))

    # 更新公開版日期索引（靜態 JSON）
    index_file = PROJECT_DIR / "public" / "data" / "index.json"
    existing_dates = []
    if index_file.exists():
        existing = json.loads(index_file.read_text())
        existing_dates = existing.get("dates", [])

    new_dates = [d["date"] for d in daily_public]
    all_dates = sorted(set(existing_dates + new_dates), reverse=True)

    existing_weekly = []
    if index_file.exists():
        existing = json.loads(index_file.read_text())
        existing_weekly = existing.get("weeklyDates", [])

    weekly_dates = existing_weekly
    if weekly_public and weekly_public.get("weekEnd"):
        weekly_dates = sorted(
            set(existing_weekly + [weekly_public["weekEnd"]]), reverse=True
        )

    index = {"dates": all_dates, "weeklyDates": weekly_dates}
    index_file.write_text(json.dumps(index, ensure_ascii=False, indent=2))
    print(f"  [FILE] public/data/index.json updated ({len(all_dates)} dates)")

    # 透過 git push 觸發 CI/CD 部署
    print("\nPushing to GitHub (triggers CI/CD deploy)...")
    dates_str = ", ".join(d["date"] for d in daily_public)
    commit_msg = f"data: add daily summary for {dates_str}"

    git_cmds = [
        ["git", "add", "public/data/"],
        ["git", "commit", "-m", commit_msg],
        ["git", "push"],
    ]
    for cmd in git_cmds:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=PROJECT_DIR
        )
        if result.returncode != 0:
            print(f"  [ERROR] {' '.join(cmd)} failed: {result.stderr[:300]}")
            return False
    print("  [OK] Pushed to GitHub → CI/CD will deploy")
    return True
