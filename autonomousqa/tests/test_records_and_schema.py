"""Record writing is append-only and records conform to the schema."""
import json
from pathlib import Path

import pytest

from runner.records import ReportWriter, load_reports
from tests.test_scoring import make_record


def test_writer_streams_then_finalizes(tmp_path: Path):
    writer = ReportWriter("t", results_dir=tmp_path)
    writer.append(make_record())
    assert writer.partial_path.is_file()
    path = writer.finalize()
    assert path.is_file() and not writer.partial_path.exists()
    assert load_reports([path])[0]["record_id"] == "abc123def456"


def test_finalize_never_overwrites(tmp_path: Path):
    writer = ReportWriter("t", results_dir=tmp_path)
    writer.append(make_record())
    first = writer.finalize()
    again = ReportWriter("t", results_dir=tmp_path)
    again.stamp = writer.stamp  # force the collision
    again.append(make_record())
    second = again.finalize()
    assert first != second and first.is_file() and second.is_file()


def test_records_conform_to_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(
        (Path(__file__).resolve().parent.parent / "schema" / "run_record.schema.json")
        .read_text())
    jsonschema.validate(make_record(), schema)


def test_shipped_illustration_results_conform_to_schema():
    jsonschema = pytest.importorskip("jsonschema")
    root = Path(__file__).resolve().parent.parent
    schema = json.loads((root / "schema" / "run_record.schema.json").read_text())
    reports = sorted((root / "results").glob("run-*.json"))
    assert reports, "no shipped result sets found"
    for record in load_reports(reports):
        jsonschema.validate(record, schema)
