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
