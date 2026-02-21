"""generate.py 的自動化測試。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from generate import extract_json


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
    import json
    text = '{"summary": "第一行\\n第二行\\n第三行"}'
    result = extract_json(text)
    parsed = json.loads(result)
    assert "\n" in parsed["summary"]
