"""Central SQLAlchemy model import registry."""

from __future__ import annotations


def register_models() -> None:
    """Import all modules that declare SQLAlchemy models before metadata use."""
    import app.ai.config  # noqa: F401
    import app.agents.models  # noqa: F401
    import app.cases.ai_suggestions  # noqa: F401
    import app.cases.diff_models  # noqa: F401
    import app.cases.domain  # noqa: F401
    import app.cases.import_models  # noqa: F401
    import app.cases.modules  # noqa: F401
    import app.cases.review_models  # noqa: F401
    import app.git.models  # noqa: F401
    import app.planning.release_reports  # noqa: F401
    import app.planning.test_plans  # noqa: F401
    import app.workspace.routes  # noqa: F401
