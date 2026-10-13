"""Tests for build_all with fake builders (no lake needed)."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest

import build_all as ba
import profiles_common as pc


def _fake(name, rows):
    def build(lake, last_updated):
        return {"family": name, "inputs": [f"{name}/in"],
                "files": [{"path": f"{name}/x.parquet", "rows": rows, "sha256": "ab"}],
                "notes": {"count": np.int64(rows), "nested": {"k": np.float64(1.5)}}}
    return SimpleNamespace(build=build)


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(ba, "BUILDERS", {"A": _fake("A", 3), "B": _fake("B", 4)})
    monkeypatch.setattr(ba, "MANIFEST", tmp_path / "BUILD_MANIFEST.json")
    monkeypatch.setattr(pc, "lake_root", lambda: tmp_path)
    day = {"d": datetime(2026, 9, 1, tzinfo=timezone.utc)}
    monkeypatch.setattr(pc, "resolve_cutoff", lambda as_of=None: day["d"])
    return tmp_path / "BUILD_MANIFEST.json", day


def test_manifest_content_and_determinism(setup):
    path, _ = setup
    m = ba.main([])
    first = path.read_bytes()
    ba.main([])
    assert path.read_bytes() == first                              # no wall-clock time inside
    assert m["profiles_last_updated"] == "2026-09-01" and list(m["families"]) == ["A", "B"]
    assert json.loads(first)["families"]["A"]["notes"] == {"count": 3, "nested": {"k": 1.5}}
    assert first.decode("ascii")                                    # plain ASCII


def test_only_keeps_other_families(setup):
    path, _ = setup
    ba.main([])
    m = ba.main(["--only", "B"])
    assert list(m["families"]) == ["A", "B"]


def test_only_refuses_to_mix_dates(setup):
    path, day = setup
    ba.main([])
    day["d"] = datetime(2026, 9, 2, tzinfo=timezone.utc)
    with pytest.raises(pc.ProfilesError, match="mix last-updated dates"):
        ba.main(["--only", "A"])


def test_unknown_family_fails_loud(setup):
    with pytest.raises(pc.ProfilesError, match="unknown families"):
        ba.main(["--only", "Nope"])
