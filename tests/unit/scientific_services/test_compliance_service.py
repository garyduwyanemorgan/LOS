"""Unit tests for the Compliance Service."""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.scientific_services.compliance.models import (
    ComplianceLevel,
    ComplianceStatus,
    ComplianceViolation,
    ParameterCompliance,
)
from backend.scientific_services.compliance.service import ComplianceService


# ── Model tests ───────────────────────────────────────────────────────────────

class TestParameterCompliance:
    def test_to_dict_structure(self) -> None:
        pc = ParameterCompliance(
            parameter="do_mg_l",
            value=3.5,
            unit="mg/L",
            limit_type="min",
            limit_value=4.0,
            level=ComplianceLevel.VIOLATION,
            margin_pct=-12.5,
            standard="UAE EA",
        )
        d = pc.to_dict()
        assert d["parameter"] == "do_mg_l"
        assert d["value"] == 3.5
        assert d["level"] == "violation"
        assert d["margin_pct"] == -12.5

    def test_unknown_level_when_value_none(self) -> None:
        pc = ParameterCompliance(
            parameter="do_mg_l",
            value=None,
            unit="mg/L",
            limit_type="min",
            limit_value=4.0,
            level=ComplianceLevel.UNKNOWN,
        )
        assert pc.level == ComplianceLevel.UNKNOWN


class TestComplianceViolation:
    def test_to_dict_serialises_level(self) -> None:
        v = ComplianceViolation(
            parameter="do_mg_l",
            value=1.5,
            unit="mg/L",
            limit_breached=4.0,
            level=ComplianceLevel.CRITICAL,
            description="DO critically low",
            recommended_action="Increase aeration",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )
        d = v.to_dict()
        assert d["level"] == "critical"
        assert "2026-01-01" in d["timestamp"]


class TestComplianceStatus:
    def test_to_dict_structure(self) -> None:
        now = datetime.now(tz=UTC)
        status = ComplianceStatus(
            lagoon_id=uuid.uuid4(),
            timestamp=now,
            overall_level=ComplianceLevel.COMPLIANT,
            confidence=0.9,
            data_completeness_pct=95.0,
        )
        d = status.to_dict()
        assert d["overall_level"] == "compliant"
        assert d["confidence"] == 0.9
        assert isinstance(d["parameters"], list)
        assert isinstance(d["violations"], list)


# ── Service tests ─────────────────────────────────────────────────────────────

class TestComplianceServiceParameterEvaluation:
    def _make_service(self) -> ComplianceService:
        return ComplianceService(shared_memory=None, event_bus=None)

    def test_min_limit_violation(self) -> None:
        svc = self._make_service()
        cfg = {"limit_type": "min", "limit_value": 4.0, "unit": "mg/L", "standard": "test"}
        pc = svc._evaluate_parameter("do_mg_l", 2.0, cfg, datetime.now(tz=UTC))
        assert pc.level == ComplianceLevel.VIOLATION

    def test_min_limit_critical(self) -> None:
        svc = self._make_service()
        cfg = {
            "limit_type": "min",
            "limit_value": 4.0,
            "critical_value": 2.0,
            "unit": "mg/L",
            "standard": "test",
        }
        pc = svc._evaluate_parameter("do_mg_l", 1.5, cfg, datetime.now(tz=UTC))
        assert pc.level == ComplianceLevel.CRITICAL

    def test_min_limit_compliant(self) -> None:
        svc = self._make_service()
        cfg = {"limit_type": "min", "limit_value": 4.0, "unit": "mg/L", "standard": "test"}
        pc = svc._evaluate_parameter("do_mg_l", 6.5, cfg, datetime.now(tz=UTC))
        assert pc.level == ComplianceLevel.COMPLIANT

    def test_max_limit_violation(self) -> None:
        svc = self._make_service()
        cfg = {
            "limit_type": "max",
            "limit_value": 50.0,
            "warning_value": 20.0,
            "unit": "NTU",
            "standard": "test",
        }
        pc = svc._evaluate_parameter("turbidity_ntu", 75.0, cfg, datetime.now(tz=UTC))
        assert pc.level == ComplianceLevel.VIOLATION

    def test_max_limit_warning(self) -> None:
        svc = self._make_service()
        cfg = {
            "limit_type": "max",
            "limit_value": 50.0,
            "warning_value": 20.0,
            "unit": "NTU",
            "standard": "test",
        }
        pc = svc._evaluate_parameter("turbidity_ntu", 30.0, cfg, datetime.now(tz=UTC))
        assert pc.level == ComplianceLevel.WARNING

    def test_max_limit_compliant(self) -> None:
        svc = self._make_service()
        cfg = {
            "limit_type": "max",
            "limit_value": 50.0,
            "warning_value": 20.0,
            "unit": "NTU",
            "standard": "test",
        }
        pc = svc._evaluate_parameter("turbidity_ntu", 10.0, cfg, datetime.now(tz=UTC))
        assert pc.level == ComplianceLevel.COMPLIANT

    def test_range_limit_violation_below(self) -> None:
        svc = self._make_service()
        cfg = {
            "limit_type": "range",
            "limit_min": 6.5,
            "limit_max": 9.0,
            "warning_min": 7.0,
            "warning_max": 8.5,
            "unit": "pH",
            "standard": "test",
        }
        pc = svc._evaluate_parameter("ph", 6.0, cfg, datetime.now(tz=UTC))
        assert pc.level == ComplianceLevel.VIOLATION

    def test_range_limit_warning(self) -> None:
        svc = self._make_service()
        cfg = {
            "limit_type": "range",
            "limit_min": 6.5,
            "limit_max": 9.0,
            "warning_min": 7.0,
            "warning_max": 8.5,
            "unit": "pH",
            "standard": "test",
        }
        pc = svc._evaluate_parameter("ph", 6.8, cfg, datetime.now(tz=UTC))
        assert pc.level == ComplianceLevel.WARNING

    def test_range_limit_compliant(self) -> None:
        svc = self._make_service()
        cfg = {
            "limit_type": "range",
            "limit_min": 6.5,
            "limit_max": 9.0,
            "warning_min": 7.0,
            "warning_max": 8.5,
            "unit": "pH",
            "standard": "test",
        }
        pc = svc._evaluate_parameter("ph", 7.8, cfg, datetime.now(tz=UTC))
        assert pc.level == ComplianceLevel.COMPLIANT

    def test_none_value_returns_unknown(self) -> None:
        svc = self._make_service()
        cfg = {"limit_type": "min", "limit_value": 4.0, "unit": "mg/L", "standard": "test"}
        pc = svc._evaluate_parameter("do_mg_l", None, cfg, datetime.now(tz=UTC))
        assert pc.level == ComplianceLevel.UNKNOWN


class TestComplianceServiceEvaluateLagoon:
    def test_evaluate_lagoon_no_shared_memory(self) -> None:
        svc = ComplianceService(shared_memory=None, event_bus=None)
        lagoon_id = uuid.uuid4()
        status = asyncio.run(svc.evaluate_lagoon(lagoon_id))
        assert isinstance(status, ComplianceStatus)
        assert status.lagoon_id == lagoon_id
        # All measurements unknown — overall should be unknown
        assert status.overall_level in (ComplianceLevel.UNKNOWN, ComplianceLevel.COMPLIANT)

    def test_evaluate_lagoon_with_violations(self) -> None:
        mock_sm = MagicMock()
        mock_sm.get = AsyncMock(return_value={
            "do_mg_l": 1.0,   # critical (< 2.0)
            "ph": 9.5,         # violation (> 9.0)
            "turbidity_ntu": 5.0,
            "tss_mg_l": None,
            "tn_mg_l": None,
            "tp_mg_l": None,
            "orp_mv": 50.0,
            "conductivity_us_cm": 1000.0,
        })
        svc = ComplianceService(shared_memory=mock_sm, event_bus=None)
        lagoon_id = uuid.uuid4()
        status = asyncio.run(svc.evaluate_lagoon(lagoon_id))
        assert status.overall_level in (ComplianceLevel.CRITICAL, ComplianceLevel.VIOLATION)
        assert status.critical_count > 0 or status.violations_count > 0

    def test_evaluate_lagoon_all_compliant(self) -> None:
        mock_sm = MagicMock()
        mock_sm.get = AsyncMock(return_value={
            "do_mg_l": 8.0,
            "ph": 7.8,
            "turbidity_ntu": 5.0,
            "tss_mg_l": 10.0,
            "tn_mg_l": 2.0,
            "tp_mg_l": 0.2,
            "orp_mv": 150.0,
            "conductivity_us_cm": 2000.0,
        })
        svc = ComplianceService(shared_memory=mock_sm, event_bus=None)
        lagoon_id = uuid.uuid4()
        status = asyncio.run(svc.evaluate_lagoon(lagoon_id))
        assert status.overall_level == ComplianceLevel.COMPLIANT
        assert status.violations_count == 0
        assert status.critical_count == 0

    def test_health_returns_dict(self) -> None:
        svc = ComplianceService(shared_memory=None, event_bus=None)
        h = asyncio.run(svc.health())
        assert h["service"] == "compliance"
        assert "status" in h

    def test_recommended_action_urgent_prefix_for_critical(self) -> None:
        action = ComplianceService._recommended_action("do_mg_l", ComplianceLevel.CRITICAL)
        assert action.startswith("URGENT:")

    def test_recommended_action_no_prefix_for_warning(self) -> None:
        action = ComplianceService._recommended_action("ph", ComplianceLevel.WARNING)
        assert not action.startswith("URGENT:")
