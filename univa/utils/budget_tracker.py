"""
Budget Tracker — Tracks LLM token usage, video generation time, and API call
costs across a pipeline execution.

Used by PipelineOrchestrator and Executive Producer skills to provide
transparent cost reporting at pipeline completion.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import time
import logging
import math

logger = logging.getLogger(__name__)

# ── Default pricing (USD per 1K tokens) ──────────────────────────────────
# These are approximate and configurable per model.

DEFAULT_PRICING = {
    # Input / Output per 1K tokens
    "gpt-5": (0.015, 0.060),
    "gpt-4o": (0.0025, 0.010),
    "gpt-4o-mini": (0.00015, 0.0006),
    "deepseek-chat": (0.00014, 0.00028),
    "deepseek-reasoner": (0.00055, 0.00219),
    "claude-sonnet-4-20250514": (0.003, 0.015),
    "claude-opus-4-20250514": (0.015, 0.075),
    "gemini-2.5-pro": (0.00125, 0.010),
    "qwen-plus": (0.0005, 0.002),
    "qwen-max": (0.0025, 0.010),
    # Fallback
    "default": (0.002, 0.008),
}

# ── Video API cost estimates ─────────────────────────────────────────────

VIDEO_API_COST_PER_CALL = 0.05   # Approximate per Wavespeed API call
IMAGE_API_COST_PER_CALL = 0.01   # Approximate per image generation


@dataclass
class LLMCallRecord:
    """Record of a single LLM invocation."""
    model: str
    tokens_in: int
    tokens_out: int
    stage: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def cost_usd(self) -> float:
        in_price, out_price = DEFAULT_PRICING.get(
            self.model,
            DEFAULT_PRICING["default"]
        )
        return (self.tokens_in / 1000) * in_price + (self.tokens_out / 1000) * out_price


@dataclass
class ToolCallRecord:
    """Record of a single MCP tool invocation."""
    tool_name: str
    duration_seconds: float
    stage: str = ""
    actual_cost_usd: Optional[float] = None
    provider_task_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    @property
    def estimated_cost_usd(self) -> float:
        """Estimate cost based on tool type."""
        if "video" in self.tool_name.lower():
            return VIDEO_API_COST_PER_CALL
        elif "image" in self.tool_name.lower():
            return IMAGE_API_COST_PER_CALL
        return 0.0

    @property
    def effective_cost_usd(self) -> float:
        """Use a provider-reported cost when present, otherwise the estimate."""
        if self.actual_cost_usd is not None:
            return self.actual_cost_usd
        return self.estimated_cost_usd


class BudgetTracker:
    """
    Accumulates LLM and tool-call costs across a pipeline execution.

    Usage:
        tracker = BudgetTracker(budget_limit_usd=1.50, model="gpt-5")
        tracker.record_llm_call(tokens_in=500, tokens_out=200, stage="proposal")
        tracker.record_tool_call("text2video_gen", duration_seconds=12.3, stage="generate")
        print(tracker.summary())
    """

    def __init__(self, budget_limit_usd: float = 1.50, model: str = "gpt-5"):
        self.budget_limit_usd = budget_limit_usd
        self.model = model
        self.llm_calls: List[LLMCallRecord] = []
        self.tool_calls: List[ToolCallRecord] = []
        self._start_time: float = time.time()

    # ── Recording methods ────────────────────────────────────────────────

    def record_llm_call(
        self,
        tokens_in: int = 0,
        tokens_out: int = 0,
        stage: str = "",
    ) -> None:
        """Record an LLM call with token counts."""
        record = LLMCallRecord(
            model=self.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            stage=stage,
        )
        self.llm_calls.append(record)
        logger.debug(
            f"LLM call recorded: stage={stage}, "
            f"in={tokens_in}, out={tokens_out}, "
            f"cost=${record.cost_usd:.4f}"
        )

    def record_tool_call(
        self,
        tool_name: str,
        duration_seconds: float,
        stage: str = "",
        actual_cost_usd: Optional[float] = None,
        provider_task_id: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        """Record an MCP tool call with timing and optional provider billing."""
        normalized_actual_cost = self._optional_nonnegative_float(actual_cost_usd)
        record = ToolCallRecord(
            tool_name=tool_name,
            duration_seconds=duration_seconds,
            stage=stage,
            actual_cost_usd=normalized_actual_cost,
            provider_task_id=str(provider_task_id) if provider_task_id is not None else None,
            provider=str(provider) if provider is not None else None,
            model=str(model) if model is not None else None,
        )
        self.tool_calls.append(record)
        logger.debug(
            f"Tool call recorded: stage={stage}, tool={tool_name}, "
            f"duration={duration_seconds:.1f}s, "
            f"cost=${record.effective_cost_usd:.4f}, "
            f"basis={'actual' if record.actual_cost_usd is not None else 'estimated'}"
        )

    # ── Computed properties ──────────────────────────────────────────────

    @property
    def total_tokens_in(self) -> int:
        return sum(c.tokens_in for c in self.llm_calls)

    @property
    def total_tokens_out(self) -> int:
        return sum(c.tokens_out for c in self.llm_calls)

    @property
    def total_tokens(self) -> int:
        return self.total_tokens_in + self.total_tokens_out

    @property
    def llm_cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.llm_calls)

    @property
    def tool_cost_usd(self) -> float:
        """Effective tool cost: actual provider cost with estimate fallback."""
        return sum(c.effective_cost_usd for c in self.tool_calls)

    @property
    def tool_actual_cost_usd(self) -> float:
        return sum(c.actual_cost_usd or 0.0 for c in self.tool_calls)

    @property
    def tool_estimated_cost_usd(self) -> float:
        return sum(c.estimated_cost_usd for c in self.tool_calls)

    @property
    def tool_fallback_estimated_cost_usd(self) -> float:
        return sum(
            c.estimated_cost_usd
            for c in self.tool_calls
            if c.actual_cost_usd is None
        )

    @property
    def total_spent_usd(self) -> float:
        return self.llm_cost_usd + self.tool_cost_usd

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.budget_limit_usd - self.total_spent_usd)

    @property
    def total_api_calls(self) -> int:
        return len(self.llm_calls) + len(self.tool_calls)

    @property
    def total_duration_seconds(self) -> float:
        return sum(c.duration_seconds for c in self.tool_calls)

    @property
    def elapsed_wall_seconds(self) -> float:
        return time.time() - self._start_time

    @property
    def is_over_budget(self) -> bool:
        return self.total_spent_usd >= self.budget_limit_usd

    @property
    def budget_usage_pct(self) -> float:
        if self.budget_limit_usd <= 0:
            return 100.0
        return (self.total_spent_usd / self.budget_limit_usd) * 100.0

    # ── Stage breakdown ──────────────────────────────────────────────────

    def stage_breakdown(self) -> Dict[str, Dict[str, Any]]:
        """Return per-stage cost breakdown."""
        stages: Dict[str, Dict[str, Any]] = {}
        for c in self.llm_calls:
            s = c.stage or "unknown"
            if s not in stages:
                stages[s] = {"llm_calls": 0, "llm_cost": 0.0, "tokens": 0,
                             "tool_calls": 0, "tool_cost": 0.0,
                             "tool_actual_cost": 0.0,
                             "tool_estimated_cost": 0.0,
                             "tool_fallback_estimated_cost": 0.0,
                             "tool_time": 0.0}
            stages[s]["llm_calls"] += 1
            stages[s]["llm_cost"] += c.cost_usd
            stages[s]["tokens"] += c.tokens_in + c.tokens_out
        for c in self.tool_calls:
            s = c.stage or "unknown"
            if s not in stages:
                stages[s] = {"llm_calls": 0, "llm_cost": 0.0, "tokens": 0,
                             "tool_calls": 0, "tool_cost": 0.0,
                             "tool_actual_cost": 0.0,
                             "tool_estimated_cost": 0.0,
                             "tool_fallback_estimated_cost": 0.0,
                             "tool_time": 0.0}
            stages[s]["tool_calls"] += 1
            stages[s]["tool_cost"] += c.effective_cost_usd
            stages[s]["tool_actual_cost"] += c.actual_cost_usd or 0.0
            stages[s]["tool_estimated_cost"] += c.estimated_cost_usd
            if c.actual_cost_usd is None:
                stages[s]["tool_fallback_estimated_cost"] += c.estimated_cost_usd
            stages[s]["tool_time"] += c.duration_seconds
        return stages

    # ── Summary ──────────────────────────────────────────────────────────

    def summary(self) -> Dict[str, Any]:
        """Return a comprehensive budget summary dict."""
        return {
            "budget_limit_usd": self.budget_limit_usd,
            "total_spent_usd": round(self.total_spent_usd, 4),
            "remaining_usd": round(self.remaining_usd, 4),
            "budget_usage_pct": round(self.budget_usage_pct, 1),
            "is_over_budget": self.is_over_budget,
            "llm": {
                "calls": len(self.llm_calls),
                "tokens_in": self.total_tokens_in,
                "tokens_out": self.total_tokens_out,
                "total_tokens": self.total_tokens,
                "cost_usd": round(self.llm_cost_usd, 4),
            },
            "tools": {
                "calls": len(self.tool_calls),
                "total_duration_seconds": round(self.total_duration_seconds, 1),
                "effective_cost_usd": round(self.tool_cost_usd, 4),
                "actual_cost_usd": round(self.tool_actual_cost_usd, 4),
                "estimated_cost_usd": round(self.tool_estimated_cost_usd, 4),
                "fallback_estimated_cost_usd": round(
                    self.tool_fallback_estimated_cost_usd, 4
                ),
            },
            "total_api_calls": self.total_api_calls,
            "elapsed_wall_seconds": round(self.elapsed_wall_seconds, 1),
            "stage_breakdown": {
                k: {kk: round(vv, 4) if isinstance(vv, float) else vv
                    for kk, vv in v.items()}
                for k, v in self.stage_breakdown().items()
            },
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the tracker so a paused pipeline can be restored."""
        return {
            "budget_limit_usd": self.budget_limit_usd,
            "model": self.model,
            "llm_calls": [
                {
                    "model": call.model,
                    "tokens_in": call.tokens_in,
                    "tokens_out": call.tokens_out,
                    "stage": call.stage,
                    "timestamp": call.timestamp,
                }
                for call in self.llm_calls
            ],
            "tool_calls": [
                {
                    "tool_name": call.tool_name,
                    "duration_seconds": call.duration_seconds,
                    "stage": call.stage,
                    "actual_cost_usd": call.actual_cost_usd,
                    "provider_task_id": call.provider_task_id,
                    "provider": call.provider,
                    "model": call.model,
                    "timestamp": call.timestamp,
                }
                for call in self.tool_calls
            ],
            "start_time": self._start_time,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "BudgetTracker":
        """Restore a tracker written by :meth:`to_dict`.

        Unknown fields are ignored to keep persisted state forward compatible.
        """
        data = data or {}
        tracker = cls(
            budget_limit_usd=float(data.get("budget_limit_usd", 1.50)),
            model=str(data.get("model", "gpt-5")),
        )
        tracker.llm_calls = [
            LLMCallRecord(
                model=str(record.get("model", tracker.model)),
                tokens_in=int(record.get("tokens_in", 0)),
                tokens_out=int(record.get("tokens_out", 0)),
                stage=str(record.get("stage", "")),
                timestamp=float(record.get("timestamp", time.time())),
            )
            for record in data.get("llm_calls", [])
            if isinstance(record, dict)
        ]
        tracker.tool_calls = [
            ToolCallRecord(
                tool_name=str(record.get("tool_name", "unknown")),
                duration_seconds=float(record.get("duration_seconds", 0.0)),
                stage=str(record.get("stage", "")),
                actual_cost_usd=cls._optional_nonnegative_float(
                    record.get("actual_cost_usd")
                ),
                provider_task_id=(
                    str(record["provider_task_id"])
                    if record.get("provider_task_id") is not None else None
                ),
                provider=(
                    str(record["provider"])
                    if record.get("provider") is not None else None
                ),
                model=(
                    str(record["model"])
                    if record.get("model") is not None else None
                ),
                timestamp=float(record.get("timestamp", time.time())),
            )
            for record in data.get("tool_calls", [])
            if isinstance(record, dict)
        ]
        if data.get("start_time") is not None:
            tracker._start_time = float(data["start_time"])
        return tracker

    @staticmethod
    def _optional_nonnegative_float(value: Any) -> Optional[float]:
        """Normalize common provider cost formats without treating bad data as zero."""
        if value is None or isinstance(value, bool):
            return None
        try:
            normalized = str(value).strip().replace("$", "").replace(",", "")
            parsed = float(normalized)
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) and parsed >= 0 else None

    # ── Estimate tokens from text (fallback when API doesn't report) ─────

    @staticmethod
    def estimate_tokens(text: str, language: str = "auto") -> int:
        """
        Rough token estimation when API usage metadata is unavailable.

        Rules of thumb (conservative):
          - English: ~4 characters per token
          - CJK: ~2 characters per token
          - Mixed: ~3 characters per token
        """
        if not text:
            return 0
        # Detect if predominantly CJK
        cjk_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        total_chars = len(text)
        if cjk_chars / max(total_chars, 1) > 0.3:
            # Mixed or CJK-dominant
            return max(1, total_chars // 2)
        return max(1, total_chars // 4)

    # ── Reset ────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset all counters for a new pipeline run."""
        self.llm_calls.clear()
        self.tool_calls.clear()
        self._start_time = time.time()
