"""util.io: atomic writes and crash-tolerant JSONL reads."""

import json

import pytest

from util.io import atomic_write_text, read_jsonl


def test_atomic_write_replaces_and_leaves_no_tmp(tmp_path):
    target = tmp_path / "out.json"
    atomic_write_text(target, "first")
    atomic_write_text(target, "second")
    assert target.read_text(encoding="utf-8") == "second"
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def test_atomic_write_creates_parent_dirs(tmp_path):
    target = tmp_path / "a" / "b" / "out.txt"
    atomic_write_text(target, "x")
    assert target.read_text(encoding="utf-8") == "x"


def test_read_jsonl_parses_all_lines(tmp_path):
    p = tmp_path / "records.jsonl"
    recs = [{"i": 1}, {"i": 2}, {"i": 3}]
    p.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    assert read_jsonl(p) == recs


def test_read_jsonl_tolerates_truncated_last_line(tmp_path):
    p = tmp_path / "records.jsonl"
    p.write_text(
        json.dumps({"i": 1}) + "\n" + json.dumps({"i": 2}) + "\n" + '{"record": "ce',
        encoding="utf-8",
    )
    assert read_jsonl(p) == [{"i": 1}, {"i": 2}]


def test_read_jsonl_raises_on_mid_file_corruption(tmp_path):
    p = tmp_path / "records.jsonl"
    p.write_text(
        '{"broken\n' + json.dumps({"i": 2}) + "\n" + json.dumps({"i": 3}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="line 1"):
        read_jsonl(p)


def test_read_jsonl_ignores_trailing_blank_lines(tmp_path):
    p = tmp_path / "records.jsonl"
    p.write_text(json.dumps({"i": 1}) + "\n\n\n", encoding="utf-8")
    assert read_jsonl(p) == [{"i": 1}]
