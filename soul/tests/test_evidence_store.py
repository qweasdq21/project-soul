"""test_evidence_store.py — JSONL + hash chain 不可变追加与篡改检测。"""
import json
from pathlib import Path

import pytest

from soul.storage.evidence_store import EvidenceStore


@pytest.fixture
def store(tmp_path: Path) -> EvidenceStore:
    return EvidenceStore(str(tmp_path / "evidence.jsonl"))


def _event(i: int) -> dict:
    return {
        "event_id": f"ev-{i}",
        "timestamp": "2026-09-11T00:00:00Z",
        "source": "cli",
        "actor": "user",
        "event_type": "user_message",
        "raw_content": f"hello {i}",
        "normalized_content": f"hello {i}",
        "metadata": {},
    }


def test_append_first_event(store):
    stored = store.compute_and_append(_event(1))
    assert stored["previous_hash"] is None
    assert stored["hash"]
    assert store.count() == 1


def test_append_multiple(store):
    store.compute_and_append(_event(1))
    store.compute_and_append(_event(2))
    store.compute_and_append(_event(3))
    assert store.count() == 3


def test_previous_hash_links(store):
    a = store.compute_and_append(_event(1))
    b = store.compute_and_append(_event(2))
    c = store.compute_and_append(_event(3))
    assert a["previous_hash"] is None
    assert b["previous_hash"] == a["hash"]
    assert c["previous_hash"] == b["hash"]


def test_verify_chain_success(store):
    store.compute_and_append(_event(1))
    store.compute_and_append(_event(2))
    valid, msg = store.verify_chain()
    assert valid
    assert "valid" in msg.lower()


def test_tamper_detected(store):
    store.compute_and_append(_event(1))
    store.compute_and_append(_event(2))
    # 手工篡改第一条 event 的 raw_content
    p = Path(store.jsonl.path)
    lines = p.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["raw_content"] = "MALICIOUS"
    lines[0] = json.dumps(first, ensure_ascii=False, sort_keys=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # 重开 store 重新读
    store2 = EvidenceStore(str(p))
    valid, msg = store2.verify_chain()
    assert not valid
    assert "invalid" in msg.lower()