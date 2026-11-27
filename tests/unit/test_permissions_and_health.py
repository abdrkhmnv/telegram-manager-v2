from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.health import HeartbeatComponent, read_heartbeat, write_heartbeat
from app.permissions import is_owner

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)


class TestIsOwner:
    def test_exact_match_only(self) -> None:
        assert is_owner(42, 42)
        assert not is_owner(43, 42)
        assert not is_owner(None, 42)

    def test_invalid_owner_never_matches(self) -> None:
        assert not is_owner(0, 0)
        assert not is_owner(-5, -5)


class TestHeartbeat:
    def test_roundtrip_healthy(self, tmp_path: Path) -> None:
        path = tmp_path / "health.json"
        write_heartbeat(path, {"userbot": True, "control_bot": True}, NOW)
        healthy, detail = read_heartbeat(path, now=NOW + timedelta(seconds=30))
        assert healthy, detail
        assert not path.with_name("health.json.tmp").exists()

    def test_failed_component(self, tmp_path: Path) -> None:
        path = tmp_path / "health.json"
        write_heartbeat(path, {"userbot": False, "control_bot": True}, NOW)
        healthy, detail = read_heartbeat(path, now=NOW)
        assert not healthy
        assert "userbot" in detail

    def test_stale(self, tmp_path: Path) -> None:
        path = tmp_path / "health.json"
        write_heartbeat(path, {"x": True}, NOW)
        healthy, detail = read_heartbeat(path, now=NOW + timedelta(minutes=5))
        assert not healthy
        assert "eskirgan" in detail

    @pytest.mark.parametrize("content", [None, "not json", json.dumps({"ts": "bad"})])
    def test_missing_or_corrupt(self, tmp_path: Path, content: str | None) -> None:
        path = tmp_path / "health.json"
        if content is not None:
            path.write_text(content)
        healthy, _ = read_heartbeat(path, now=NOW)
        assert not healthy

    async def test_component_writes_and_removes_file(self, tmp_path: Path) -> None:
        path = tmp_path / "sub" / "health.json"

        def broken_probe() -> bool:
            raise RuntimeError("probe failed")

        component = HeartbeatComponent(path, {"ok": lambda: True, "broken": broken_probe})
        await component.start()
        payload = json.loads(path.read_text())
        assert payload["components"] == {"ok": True, "broken": False}
        await component.stop()
        assert not path.exists()

    def test_rejects_bad_interval(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            HeartbeatComponent(tmp_path / "h.json", {}, interval=0)
