"""Firestore emulator fixture acceptance (Wave-0 gate, risk R7/R1/R2)."""

from __future__ import annotations

from google.cloud import firestore


class TestEmulatorFixture:
    def test_write_read_roundtrip(self, firestore_client: firestore.Client) -> None:
        doc_ref = firestore_client.collection("smoke").document("roundtrip")
        doc_ref.set({"value": 41, "label": "hello"})
        snapshot = doc_ref.get()
        assert snapshot.exists
        assert snapshot.to_dict() == {"value": 41, "label": "hello"}

    def test_per_test_project_isolation(
        self, firestore_client: firestore.Client, unique_project: str
    ) -> None:
        assert unique_project.startswith("test-")
        assert firestore_client.project == unique_project
        assert not firestore_client.collection("smoke").document("roundtrip").get().exists
