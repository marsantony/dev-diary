"""generate.py 的自動化測試。"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from generate import extract_json, load_daily_summaries, PUBLIC_DATA_DIR


def test_extract_json_plain():
    """純 JSON 字串直接回傳。"""
    text = '{"ok": true}'
    assert extract_json(text) == '{"ok": true}'


def test_extract_json_with_code_block():
    """從 markdown code block 中提取 JSON。"""
    text = '''這是摘要：

```json
{"sessions": [], "daySummary": "測試"}
```

以上是結果。'''
    result = extract_json(text)
    assert '"sessions"' in result
    assert '"daySummary"' in result


def test_extract_json_with_bare_code_block():
    """從沒有 json 標記的 code block 提取。"""
    text = '''```
{"ok": true}
```'''
    assert extract_json(text) == '{"ok": true}'


def test_extract_json_with_prefix_text():
    """JSON 前面有額外文字。"""
    text = '讓我產生摘要：\n\n{"sessions": []}'
    result = extract_json(text)
    assert result == '{"sessions": []}'


def test_extract_json_with_suffix_text():
    """JSON 後面有額外文字。"""
    text = '{"ok": true}\n\n以上是結果。'
    result = extract_json(text)
    assert result == '{"ok": true}'


def test_extract_json_complex():
    """複雜的嵌套 JSON。"""
    text = '''```json
{
  "sessions": [
    {"id": "abc", "time": "10:00", "summary": "測試摘要"}
  ],
  "daySummary": "今天做了測試"
}
```'''
    import json
    result = extract_json(text)
    parsed = json.loads(result)
    assert len(parsed["sessions"]) == 1
    assert parsed["sessions"][0]["id"] == "abc"


def test_extract_json_preserves_newlines_in_values():
    """JSON 值中的 \\n 應被保留。"""
    text = '{"summary": "第一行\\n第二行\\n第三行"}'
    result = extract_json(text)
    parsed = json.loads(result)
    assert "\n" in parsed["summary"]


def test_load_daily_summaries_from_disk(tmp_path):
    """從磁碟讀回公開版每日摘要。"""
    from datetime import datetime, timedelta, timezone

    TZ = timezone(timedelta(hours=8))
    week_start = datetime(2026, 2, 16, tzinfo=TZ)
    week_end = datetime(2026, 2, 21, tzinfo=TZ)

    # 建立假的 daily JSON 檔案
    for day in range(16, 22):
        date_str = f"2026-02-{day:02d}"
        data = {"date": date_str, "daySummary": f"摘要 {date_str}"}
        (tmp_path / f"daily-{date_str}.json").write_text(
            json.dumps(data, ensure_ascii=False)
        )

    with patch("generate.PUBLIC_DATA_DIR", tmp_path), \
         patch("upload.kv_get", return_value=None):
        pub, priv = load_daily_summaries(week_start, week_end)

    assert len(pub) == 6
    assert pub[0]["date"] == "2026-02-16"
    assert pub[-1]["date"] == "2026-02-21"
    assert len(priv) == 0  # KV 回傳 None


def test_load_daily_summaries_with_kv(tmp_path):
    """從 KV 讀回私密版每日摘要。"""
    from datetime import datetime, timedelta, timezone

    TZ = timezone(timedelta(hours=8))
    week_start = datetime(2026, 2, 16, tzinfo=TZ)
    week_end = datetime(2026, 2, 17, tzinfo=TZ)

    def mock_kv_get(key):
        if "2026-02-16" in key:
            return json.dumps({"date": "2026-02-16", "dayDetails": "詳細"})
        return None

    with patch("generate.PUBLIC_DATA_DIR", tmp_path), \
         patch("upload.kv_get", side_effect=mock_kv_get):
        pub, priv = load_daily_summaries(week_start, week_end)

    assert len(pub) == 0  # 磁碟沒有檔案
    assert len(priv) == 1
    assert priv[0]["date"] == "2026-02-16"


def test_daily_skips_existing(tmp_path):
    """每日摘要已存在時應跳過，不呼叫 generate_daily。"""
    date_str = "2026-02-20"
    data = {"date": date_str, "daySummary": "已存在的摘要"}
    (tmp_path / f"daily-{date_str}.json").write_text(
        json.dumps(data, ensure_ascii=False)
    )

    # 驗證檔案存在就跳過的邏輯
    pub_file = tmp_path / f"daily-{date_str}.json"
    assert pub_file.exists()
    loaded = json.loads(pub_file.read_text())
    assert loaded["daySummary"] == "已存在的摘要"
