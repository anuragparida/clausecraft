"""Pipeline — public surface.

Phase 1 added :func:`run_stage1` (ingest → parse → classify).
Phase 2 adds :func:`run_stage3` (spot deviations, per-clause
parallel orchestration against the playbook). The aggregate
stage (:func:`run_stage4`, build the flag table) is a separate
card.

The stages are independent functions; the LangGraph orchestration
that wires them together is a Phase 2+ concern (the
``app.graph.graph`` module — Phase 0's echo graph is a stub).
"""

from app.pipeline.stage1_ingest import (
    Stage1Result,
    run_stage1,
)
from app.pipeline.stage3_spot import (
    Stage3Result,
    run_stage3,
)

__all__ = [
    "Stage1Result",
    "Stage3Result",
    "run_stage1",
    "run_stage3",
]
