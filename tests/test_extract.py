"""extract.py 的自動化測試。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from extract import clean_text, extract_session


def test_clean_text_removes_system_tags():
    text = 'hello <system-reminder>secret</system-reminder> world'
    assert clean_text(text) == "hello  world"


def test_clean_text_removes_ide_tags():
    text = '<ide_opened_file>/some/path</ide_opened_file>actual message'
    assert clean_text(text) == "actual message"


def test_clean_text_removes_ide_selection():
    text = 'before <ide_selection>selected code</ide_selection> after'
    assert clean_text(text) == "before  after"


def test_clean_text_preserves_normal_text():
    text = "這是一段正常的訊息"
    assert clean_text(text) == "這是一段正常的訊息"


def test_clean_text_empty_after_cleaning():
    text = '<system-reminder>only system content</system-reminder>'
    assert clean_text(text) == ""


def test_extract_session_with_valid_data(tmp_path):
    """測試從 .jsonl 提取 session 資料。"""
    session_file = tmp_path / "test-session.jsonl"
    lines = [
        {"type": "user", "timestamp": "2026-02-20T10:00:00Z", "message": {
            "content": [{"type": "text", "text": "幫我寫一個函式"}]
        }},
        {"type": "assistant", "message": {
            "content": [
                {"type": "text", "text": "好的，我來幫你寫。"},
                {"type": "tool_use", "name": "Edit", "input": {"file_path": "/tmp/test.py"}},
            ]
        }},
        {"type": "user", "message": {
            "content": [{"type": "text", "text": "謝謝"}]
        }},
    ]
    session_file.write_text("\n".join(json.dumps(l, ensure_ascii=False) for l in lines))

    result = extract_session(session_file)

    assert result is not None
    assert result["id"] == "test-ses"  # filepath.stem[:8]
    assert result["message_count"] == 2
    assert len(result["user_messages"]) == 2
    assert "幫我寫一個函式" in result["user_messages"][0]
    assert "Edit" in result["tools_used"]
    assert "/tmp/test.py" in result["files_edited"]


def test_extract_session_empty_session(tmp_path):
    """沒有 user 訊息的 session 應回傳 None。"""
    session_file = tmp_path / "empty.jsonl"
    lines = [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}},
    ]
    session_file.write_text("\n".join(json.dumps(l) for l in lines))

    result = extract_session(session_file)
    assert result is None


def test_extract_session_tracks_git_operations(tmp_path):
    """測試 git 操作追蹤。"""
    session_file = tmp_path / "git-test.jsonl"
    lines = [
        {"type": "user", "timestamp": "2026-02-20T10:00:00Z", "message": {
            "content": [{"type": "text", "text": "幫我 commit"}]
        }},
        {"type": "assistant", "message": {
            "content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": "git commit -m 'test'"}},
                {"type": "tool_use", "name": "Bash", "input": {"command": "git push origin main"}},
            ]
        }},
    ]
    session_file.write_text("\n".join(json.dumps(l, ensure_ascii=False) for l in lines))

    result = extract_session(session_file)

    assert result is not None
    assert len(result["git_operations"]) == 2
    assert any("git commit" in op for op in result["git_operations"])
    assert any("git push" in op for op in result["git_operations"])


def test_extract_session_date_filter(tmp_path):
    """跨日 session：用 date_filter 只提取特定一天的訊息。"""
    session_file = tmp_path / "cross-day.jsonl"
    lines = [
        # Day 1: 2026-02-20
        {"type": "user", "timestamp": "2026-02-20T22:00:00Z", "message": {
            "content": [{"type": "text", "text": "第一天的訊息"}]
        }},
        {"type": "assistant", "timestamp": "2026-02-20T22:01:00Z", "message": {
            "content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "/tmp/day1.py"}}]
        }},
        # Day 2: 2026-02-21（台灣時間，UTC 2026-02-20T16:00:00 = 台灣 2026-02-21T00:00:00）
        {"type": "user", "timestamp": "2026-02-21T02:00:00Z", "message": {
            "content": [{"type": "text", "text": "第二天繼續"}]
        }},
        {"type": "assistant", "timestamp": "2026-02-21T02:05:00Z", "message": {
            "content": [{"type": "tool_use", "name": "Write", "input": {"file_path": "/tmp/day2.py"}}]
        }},
    ]
    session_file.write_text("\n".join(json.dumps(l, ensure_ascii=False) for l in lines))

    # 不帶 filter：取得所有
    result_all = extract_session(session_file)
    assert result_all is not None
    assert result_all["message_count"] == 2
    assert "/tmp/day1.py" in result_all["files_edited"]
    assert "/tmp/day2.py" in result_all["files_edited"]
    assert set(result_all["all_dates"]) == {"2026-02-21"}  # UTC+8: 22:00 UTC = 06:00+1 台灣

    # 帶 filter：只取 2026-02-21（台灣時間）
    result_day2 = extract_session(session_file, date_filter="2026-02-21")
    assert result_day2 is not None
    assert result_day2["message_count"] == 2  # 兩筆都是 UTC+8 的 2/21
    assert "2026-02-21" in result_day2["all_dates"]

    # 帶 filter：2026-02-19 沒有訊息
    result_none = extract_session(session_file, date_filter="2026-02-19")
    assert result_none is None


def test_extract_session_cross_day_split(tmp_path):
    """跨日 session 正確拆分到不同天。"""
    session_file = tmp_path / "spanning.jsonl"
    lines = [
        # 台灣時間 2/20 23:00（UTC 2/20 15:00）
        {"type": "user", "timestamp": "2026-02-20T15:00:00Z", "message": {
            "content": [{"type": "text", "text": "晚上開始工作"}]
        }},
        {"type": "assistant", "timestamp": "2026-02-20T15:05:00Z", "message": {
            "content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "/tmp/a.py"}}]
        }},
        # 台灣時間 2/21 01:00（UTC 2/20 17:00）
        {"type": "user", "timestamp": "2026-02-20T17:00:00Z", "message": {
            "content": [{"type": "text", "text": "跨過午夜了"}]
        }},
        {"type": "assistant", "timestamp": "2026-02-20T17:05:00Z", "message": {
            "content": [{"type": "tool_use", "name": "Write", "input": {"file_path": "/tmp/b.py"}}]
        }},
    ]
    session_file.write_text("\n".join(json.dumps(l, ensure_ascii=False) for l in lines))

    # 2/20 台灣時間：只有第一組訊息
    result_20 = extract_session(session_file, date_filter="2026-02-20")
    assert result_20 is not None
    assert result_20["message_count"] == 1
    assert "晚上開始工作" in result_20["user_messages"][0]
    assert "/tmp/a.py" in result_20["files_edited"]
    assert "/tmp/b.py" not in result_20["files_edited"]

    # 2/21 台灣時間：只有第二組訊息
    result_21 = extract_session(session_file, date_filter="2026-02-21")
    assert result_21 is not None
    assert result_21["message_count"] == 1
    assert "跨過午夜了" in result_21["user_messages"][0]
    assert "/tmp/b.py" in result_21["files_edited"]
    assert "/tmp/a.py" not in result_21["files_edited"]

    # all_dates 應該包含兩天
    assert set(result_20["all_dates"]) == {"2026-02-20", "2026-02-21"}
    assert set(result_21["all_dates"]) == {"2026-02-20", "2026-02-21"}


def test_extract_session_all_dates_field(tmp_path):
    """確認 all_dates 欄位正確追蹤所有日期。"""
    session_file = tmp_path / "multiday.jsonl"
    lines = [
        {"type": "user", "timestamp": "2026-02-18T10:00:00Z", "message": {
            "content": [{"type": "text", "text": "Day 1"}]
        }},
        {"type": "user", "timestamp": "2026-02-19T10:00:00Z", "message": {
            "content": [{"type": "text", "text": "Day 2"}]
        }},
        {"type": "user", "timestamp": "2026-02-20T10:00:00Z", "message": {
            "content": [{"type": "text", "text": "Day 3"}]
        }},
    ]
    session_file.write_text("\n".join(json.dumps(l, ensure_ascii=False) for l in lines))

    result = extract_session(session_file)
    assert result is not None
    assert result["all_dates"] == ["2026-02-18", "2026-02-19", "2026-02-20"]
