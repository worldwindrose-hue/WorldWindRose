"""Tests for Block 8 — ChainOfThought + UsageTracker + ImmutableKernel."""
from __future__ import annotations

import pytest
import json
import time
from pathlib import Path
from datetime import date, timedelta
from unittest.mock import patch


# ── ChainOfThought ────────────────────────────────────────────────────────


class TestChainOfThought:
    def test_cot_singleton(self):
        """get_cot_visualizer() returns same instance."""
        from core.transparency.chain_of_thought import get_cot_visualizer, ChainOfThoughtVisualizer
        a = get_cot_visualizer()
        b = get_cot_visualizer()
        assert a is b
        assert isinstance(a, ChainOfThoughtVisualizer)

    def test_extract_no_think_tags(self):
        """Response without <think> tags uses heuristic steps."""
        from core.transparency.chain_of_thought import ChainOfThoughtVisualizer
        cot = ChainOfThoughtVisualizer()
        trace = cot.extract_from_response(
            question="What is 2+2?",
            raw_response="The answer is 4.",
        )
        assert trace.question == "What is 2+2?"
        assert trace.final_answer == "The answer is 4."
        assert len(trace.steps) >= 1

    def test_extract_with_think_tags(self):
        """Response with <think>...</think> extracts reasoning steps."""
        from core.transparency.chain_of_thought import ChainOfThoughtVisualizer
        cot = ChainOfThoughtVisualizer()
        raw = "<think>\nFirst I analyze the question.\n\nThen I form the answer.\n</think>\nThe answer is 42."
        trace = cot.extract_from_response(
            question="What is the meaning of life?",
            raw_response=raw,
        )
        assert "42" in trace.final_answer
        assert "<think>" not in trace.final_answer
        assert len(trace.steps) >= 2

    def test_trace_to_dict(self):
        """CoTTrace.to_dict() is JSON-serializable."""
        from core.transparency.chain_of_thought import ChainOfThoughtVisualizer
        cot = ChainOfThoughtVisualizer()
        trace = cot.extract_from_response("question", "answer")
        d = trace.to_dict()
        assert isinstance(d, dict)
        assert "steps" in d
        assert "final_answer" in d
        json.dumps(d)  # should not raise

    def test_get_recent_traces(self):
        """get_recent_traces returns list."""
        from core.transparency.chain_of_thought import ChainOfThoughtVisualizer
        cot = ChainOfThoughtVisualizer()
        cot.extract_from_response("q1", "a1")
        cot.extract_from_response("q2", "a2")
        traces = cot.get_recent_traces(limit=10)
        assert len(traces) >= 2

    def test_get_trace_by_id(self):
        """get_trace returns trace by ID."""
        from core.transparency.chain_of_thought import ChainOfThoughtVisualizer
        cot = ChainOfThoughtVisualizer()
        trace = cot.extract_from_response("unique question", "answer", trace_id="test123")
        found = cot.get_trace("test123")
        assert found is not None
        assert found.trace_id == "test123"

    def test_get_trace_missing(self):
        """get_trace returns None for unknown ID."""
        from core.transparency.chain_of_thought import ChainOfThoughtVisualizer
        cot = ChainOfThoughtVisualizer()
        assert cot.get_trace("nonexistent_xyz") is None

    def test_max_traces_limit(self):
        """Old traces are evicted when max is reached."""
        from core.transparency.chain_of_thought import ChainOfThoughtVisualizer
        from core.transparency import chain_of_thought as cot_module
        original = cot_module._MAX_TRACES
        cot_module._MAX_TRACES = 3

        cot = ChainOfThoughtVisualizer()
        for i in range(5):
            cot.extract_from_response(f"q{i}", f"a{i}")

        assert len(cot._traces) <= 3
        cot_module._MAX_TRACES = original

    def test_think_tags_multiblock(self):
        """Multiple paragraphs in think block become multiple steps."""
        from core.transparency.chain_of_thought import ChainOfThoughtVisualizer
        cot = ChainOfThoughtVisualizer()
        raw = (
            "<think>\nPara 1 analysis here.\n\n"
            "Para 2 deeper reasoning.\n\n"
            "Para 3 conclusion.\n</think>\n"
            "Final answer text."
        )
        trace = cot.extract_from_response("question", raw)
        assert len(trace.steps) >= 2


# ── UsageTracker ──────────────────────────────────────────────────────────


class TestUsageTracker:
    def test_tracker_singleton(self):
        """get_usage_tracker() returns same instance."""
        from core.transparency.usage_report import get_usage_tracker, UsageTracker
        a = get_usage_tracker()
        b = get_usage_tracker()
        assert a is b
        assert isinstance(a, UsageTracker)

    def test_record_request(self):
        """record_request updates today's stats."""
        from core.transparency.usage_report import UsageTracker
        tracker = UsageTracker()
        initial = tracker.get_today().requests

        tracker.record_request("moonshotai/kimi-k2.5", input_tokens=100, output_tokens=200)

        today = tracker.get_today()
        assert today.requests == initial + 1
        assert today.input_tokens >= 100
        assert today.output_tokens >= 200

    def test_record_request_cached(self):
        """Cached requests increment cache_hits."""
        from core.transparency.usage_report import UsageTracker
        tracker = UsageTracker()
        initial_hits = tracker.get_today().cache_hits

        tracker.record_request("cache", cached=True)
        assert tracker.get_today().cache_hits == initial_hits + 1

    def test_record_request_error(self):
        """Error flag increments error count."""
        from core.transparency.usage_report import UsageTracker
        tracker = UsageTracker()
        initial_errors = tracker.get_today().errors

        tracker.record_request("moonshotai/kimi-k2.5", error=True)
        assert tracker.get_today().errors == initial_errors + 1

    def test_day_stats_total_tokens(self):
        """DayStats.total_tokens = input + output."""
        from core.transparency.usage_report import DayStats
        s = DayStats(date="2026-01-01", input_tokens=300, output_tokens=700)
        assert s.total_tokens == 1000

    def test_estimated_cost_free_for_cache(self):
        """Cache hits have zero cost."""
        from core.transparency.usage_report import DayStats
        s = DayStats(date="2026-01-01", models={"cache": 100})
        assert s.estimated_cost_usd == 0.0

    def test_get_week_returns_7_days(self):
        """get_week() returns exactly 7 days."""
        from core.transparency.usage_report import UsageTracker
        tracker = UsageTracker()
        week = tracker.get_week()
        assert len(week) == 7

    def test_get_totals(self):
        """get_totals returns dict with required fields."""
        from core.transparency.usage_report import UsageTracker
        tracker = UsageTracker()
        totals = tracker.get_totals(days=7)
        assert "total_requests" in totals
        assert "total_tokens" in totals
        assert "cache_hits" in totals
        assert "cache_rate" in totals

    def test_generate_weekly_report(self):
        """generate_weekly_report returns non-empty string."""
        from core.transparency.usage_report import UsageTracker
        tracker = UsageTracker()
        report = tracker.generate_weekly_report()
        assert isinstance(report, str)
        assert len(report) > 10

    def test_model_tracking(self):
        """Models are tracked per request."""
        from core.transparency.usage_report import UsageTracker
        tracker = UsageTracker()
        tracker.record_request("moonshotai/kimi-k2.5")
        tracker.record_request("ollama/local")
        today = tracker.get_today()
        assert "moonshotai/kimi-k2.5" in today.models
        assert "ollama/local" in today.models


# ── ImmutableKernel ───────────────────────────────────────────────────────


class TestImmutableKernel:
    def test_kernel_singleton(self):
        """get_immutable_kernel() returns same instance."""
        from core.security.immutable_kernel import get_immutable_kernel, ImmutableKernel
        a = get_immutable_kernel()
        b = get_immutable_kernel()
        assert a is b
        assert isinstance(a, ImmutableKernel)

    def test_seal_creates_manifest(self, tmp_path):
        """seal() records file hashes."""
        from core.security import immutable_kernel as km
        original = km._KERNEL_MANIFEST
        km._KERNEL_MANIFEST = tmp_path / "manifest.json"

        from core.security.immutable_kernel import ImmutableKernel

        # Create real files to seal
        f1 = tmp_path / "file1.py"
        f1.write_text("print('hello')")

        kernel = ImmutableKernel(files=[str(f1)])
        count = kernel.seal()

        assert count == 1
        assert km._KERNEL_MANIFEST.exists()
        km._KERNEL_MANIFEST = original

    def test_verify_ok(self, tmp_path):
        """verify() returns integrity=True when files unchanged."""
        from core.security import immutable_kernel as km
        original = km._KERNEL_MANIFEST
        km._KERNEL_MANIFEST = tmp_path / "manifest.json"

        from core.security.immutable_kernel import ImmutableKernel

        f1 = tmp_path / "core_file.py"
        f1.write_text("# core content")

        kernel = ImmutableKernel(files=[str(f1)])
        kernel.seal()
        report = kernel.verify()

        assert report.integrity is True
        assert report.modified == 0
        km._KERNEL_MANIFEST = original

    def test_verify_detects_modification(self, tmp_path):
        """verify() detects modified files."""
        from core.security import immutable_kernel as km
        original = km._KERNEL_MANIFEST
        km._KERNEL_MANIFEST = tmp_path / "manifest.json"

        from core.security.immutable_kernel import ImmutableKernel

        f1 = tmp_path / "core_file.py"
        f1.write_text("# original content")

        kernel = ImmutableKernel(files=[str(f1)])
        kernel.seal()

        # Modify file
        f1.write_text("# TAMPERED content")
        report = kernel.verify()

        assert report.integrity is False
        assert report.modified == 1
        assert len(report.violations) == 1
        km._KERNEL_MANIFEST = original

    def test_verify_detects_missing(self, tmp_path):
        """verify() detects missing files."""
        from core.security import immutable_kernel as km
        original = km._KERNEL_MANIFEST
        km._KERNEL_MANIFEST = tmp_path / "manifest.json"

        from core.security.immutable_kernel import ImmutableKernel

        f1 = tmp_path / "core_file.py"
        f1.write_text("# content")

        kernel = ImmutableKernel(files=[str(f1)])
        kernel.seal()

        # Delete file
        f1.unlink()
        report = kernel.verify()

        assert report.missing == 1
        assert report.integrity is False
        km._KERNEL_MANIFEST = original

    def test_is_sealed_false_before_seal(self, tmp_path):
        """is_sealed() returns False when manifest is empty."""
        from core.security import immutable_kernel as km
        original = km._KERNEL_MANIFEST
        km._KERNEL_MANIFEST = tmp_path / "empty_manifest.json"

        from core.security.immutable_kernel import ImmutableKernel
        kernel = ImmutableKernel(files=[])
        assert kernel.is_sealed() is False
        km._KERNEL_MANIFEST = original

    def test_report_to_dict(self, tmp_path):
        """KernelReport.to_dict() is JSON-serializable."""
        from core.security import immutable_kernel as km
        original = km._KERNEL_MANIFEST
        km._KERNEL_MANIFEST = tmp_path / "manifest.json"

        from core.security.immutable_kernel import ImmutableKernel
        f1 = tmp_path / "f.py"
        f1.write_text("x")
        kernel = ImmutableKernel(files=[str(f1)])
        kernel.seal()
        report = kernel.verify()
        d = report.to_dict()
        json.dumps(d)  # should not raise
        km._KERNEL_MANIFEST = original

    def test_hash_file_missing(self, tmp_path):
        """_hash_file returns empty string for missing file."""
        from core.security.immutable_kernel import ImmutableKernel
        kernel = ImmutableKernel()
        h, size = kernel._hash_file(tmp_path / "nonexistent.py")
        assert h == ""
        assert size == 0
