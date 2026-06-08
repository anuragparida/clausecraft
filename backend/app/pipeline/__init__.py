"""Pipeline — public surface.

Phase 1 added :func:`run_stage1` (ingest -> parse -> classify).
Phase 2 added :func:`run_stage3` (spot deviations, per-clause
parallel orchestration against the playbook).
Phase 3 adds the LangGraph HITL pipeline (interrupt, redline,
audit log). The graph is the long-running state machine; the
stages are the building blocks.

Public surface (Phase 3)
------------------------

- :func:`app.pipeline.graph_runtime.get_compiled_pipeline` —
  the compiled graph (compile-once per process).
- :func:`app.pipeline.graph_runtime.build_pipeline_for_test` —
  per-test fresh compile.
- :func:`app.pipeline.graph_runtime.build_initial_state` —
  the initial state for a new run.
- :func:`app.pipeline.graph_runtime.new_thread_id` — the
  contract id / thread id generator.

The stage functions (:func:`run_stage1`, :func:`run_stage3`)
remain the public surface for the FastAPI endpoints that
don't go through the LangGraph state machine (the Phase 1/2
``POST /contracts/ingest`` and ``POST /contracts/spot``
endpoints are unchanged for now).
"""

from app.pipeline.graph_runtime import (
    build_initial_state,
    build_pipeline_for_test,
    get_compiled_pipeline,
    new_thread_id,
)
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
    "get_compiled_pipeline",
    "build_pipeline_for_test",
    "build_initial_state",
    "new_thread_id",
]
