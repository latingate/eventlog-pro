"""The jsonl, memory and null backends."""

from __future__ import annotations

import json
import threading

import pytest

from eventlog_pro import BackendError, configure, delete_events, event_query, log_event
from eventlog_pro.config import get_backend


# ------------------------------------------------------------------- jsonl
@pytest.fixture
def jsonl_path(tmp_path):
    path = tmp_path / "nested" / "events.jsonl"
    configure(dsn=f"jsonl:///{path.as_posix()}")
    return path


def read_lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_jsonl_appends_one_object_per_line(jsonl_path):
    log_event(app="a", category="c", event_code="ONE")
    log_event(app="a", category="c", event_code="TWO", data={"n": 1})
    lines = read_lines(jsonl_path)
    assert [line["event_code"] for line in lines] == ["ONE", "TWO"]
    assert lines[1]["data"] == {"n": 1}


def test_jsonl_id_stays_none(jsonl_path):
    # A file has no sequence; inventing a counter would produce ids that
    # collide across processes.
    assert log_event(app="a", category="c", event_code="E").id is None
    assert read_lines(jsonl_path)[0]["id"] is None


def test_jsonl_created_at_is_iso_utc(jsonl_path):
    event = log_event(app="a", category="c", event_code="E")
    assert read_lines(jsonl_path)[0]["created_at"] == event.created_at.isoformat()


def test_jsonl_creates_parent_directories(jsonl_path):
    log_event(app="a", category="c", event_code="E")
    assert jsonl_path.exists()


def test_jsonl_keeps_unicode_readable(jsonl_path):
    log_event(app="a", category="c", event_code="E", remarks="שלום ✓")
    assert "שלום ✓" in jsonl_path.read_text(encoding="utf-8")


def test_jsonl_is_thread_safe(jsonl_path):
    def worker(n):
        for _ in range(20):
            log_event(app="a", category="c", event_code=f"T{n}")

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    lines = read_lines(jsonl_path)
    assert len(lines) == 80  # no interleaved or truncated writes


def test_jsonl_needs_a_path():
    configure(dsn="jsonl://")
    with pytest.raises(BackendError, match="needs a file path"):
        log_event(app="a", category="c", event_code="E")


def test_jsonl_reads_back_through_the_same_filters(jsonl_path):
    log_event(app="api", category="c", event_code="ONE", data={"invoice": "INV-1"})
    log_event(app="web", category="c", event_code="TWO")
    assert [e.event_code for e in event_query(app="api")] == ["ONE"]
    assert [e.event_code for e in event_query(data="INV-1")] == ["ONE"]
    assert [e.event_code for e in event_query(order_by="event_code")] == ["ONE", "TWO"]
    assert event_query()[0].created_at.tzinfo is not None


def test_jsonl_reads_an_absent_file_as_empty(tmp_path):
    configure(dsn=f"jsonl:///{(tmp_path / 'nothing.jsonl').as_posix()}")
    assert event_query() == []


def test_jsonl_skips_a_half_written_line(jsonl_path):
    log_event(app="a", category="c", event_code="GOOD")
    with jsonl_path.open("a", encoding="utf-8") as handle:
        handle.write('{"app": "a", "event_c\n')  # a torn final write
    assert [e.event_code for e in event_query()] == ["GOOD"]


def test_jsonl_refuses_to_delete(jsonl_path):
    log_event(app="a", category="c", event_code="E")
    with pytest.raises(BackendError, match="append-only"):
        delete_events(app="a")


# ------------------------------------------------------------------ memory
def test_memory_assigns_sequential_ids():
    configure(dsn="memory://")
    assert [log_event(app="a", category="c", event_code="E").id for _ in range(3)] == [1, 2, 3]
    assert len(get_backend().events) == 3


def test_memory_respects_max_events():
    configure(dsn="memory://?max_events=2")
    for n in range(5):
        log_event(app="a", category="c", event_code=str(n))
    kept = [event.event_code for event in get_backend().events]
    assert kept == ["3", "4"]


def test_memory_clear():
    configure(dsn="memory://")
    log_event(app="a", category="c", event_code="E")
    get_backend().clear()
    assert get_backend().events == []


def test_memory_queries_and_deletes_in_process():
    configure(dsn="memory://")
    for n in range(5):
        log_event(app="api" if n < 3 else "web", category="c", event_code=str(n))
    assert [e.event_code for e in event_query(app="api")] == ["2", "1", "0"]
    assert [e.event_code for e in event_query(limit=2, order_by="event_code")] == ["0", "1"]
    assert delete_events(app="api", limit=2) == 2
    assert [e.event_code for e in event_query(order_by="event_code")] == ["2", "3", "4"]
    assert delete_events(app="web") == 2
    assert [e.event_code for e in event_query()] == ["2"]


# -------------------------------------------------------------------- null
def test_null_accepts_and_counts_everything():
    configure(dsn="null://")
    for _ in range(3):
        assert log_event(app="a", category="c", event_code="E").id is None
    assert get_backend().dropped == 3


def test_null_reads_empty_and_deletes_nothing():
    configure(dsn="null://")
    log_event(app="a", category="c", event_code="E")
    assert event_query() == []
    assert delete_events(app="a") == 0
