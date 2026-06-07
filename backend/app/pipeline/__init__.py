"""Pipeline — public surface."""

from app.pipeline.stage1_ingest import (
    Stage1Result,
    run_stage1,
)

__all__ = ["Stage1Result", "run_stage1"]
