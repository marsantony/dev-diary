"""generate.py 的自動化測試。"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from generate import extract_json, load_daily_summaries


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


def test_load_daily_summaries_from_kv():
    """從 KV 讀回公開版和私密版每日摘要。"""
    from datetime import datetime, timedelta, timezone

    TZ = timezone(timedelta(hours=8))
    week_start = datetime(2026, 2, 16, tzinfo=TZ)
    week_end = datetime(2026, 2, 21, tzinfo=TZ)

    def mock_kv_get(key):
        # 模擬 KV 中有公開版資料
        for day in range(16, 22):
            date_str = f"2026-02-{day:02d}"
            if key == f"public:daily:{date_str}":
                return json.dumps({"date": date_str, "daySummary": f"摘要 {date_str}"})
        return None

    with patch("upload.kv_get", side_effect=mock_kv_get):
        pub, priv = load_daily_summaries(week_start, week_end)

    assert len(pub) == 6
    assert pub[0]["date"] == "2026-02-16"
    assert pub[-1]["date"] == "2026-02-21"
    assert len(priv) == 0


def test_load_daily_summaries_with_private_kv():
    """從 KV 讀回私密版每日摘要。"""
    from datetime import datetime, timedelta, timezone

    TZ = timezone(timedelta(hours=8))
    week_start = datetime(2026, 2, 16, tzinfo=TZ)
    week_end = datetime(2026, 2, 17, tzinfo=TZ)

    def mock_kv_get(key):
        if key == "private:daily:2026-02-16":
            return json.dumps({"date": "2026-02-16", "dayDetails": "詳細"})
        return None

    with patch("upload.kv_get", side_effect=mock_kv_get):
        pub, priv = load_daily_summaries(week_start, week_end)

    assert len(pub) == 0
    assert len(priv) == 1
    assert priv[0]["date"] == "2026-02-16"
