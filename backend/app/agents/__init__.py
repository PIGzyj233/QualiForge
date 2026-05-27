"""Agent domain package with backward-compatible lazy public exports."""

_SUBMODULES = {
    "activities",
    "budget",
    "coverage",
    "graph",
    "memory",
    "models",
    "repository",
    "routes",
    "schemas",
    "serializers",
    "state",
    "temporal",
    "workflow_gateway",
    "workflows",
}

_EXPORT_MODULES = (
    "app.agents.models",
    "app.agents.schemas",
    "app.agents.serializers",
    "app.agents.repository",
    "app.agents.state",
    "app.agents.budget",
    "app.agents.coverage",
    "app.agents.routes",
)


def __getattr__(name: str):
    from importlib import import_module

    if name in _SUBMODULES:
        return import_module(f"app.agents.{name}")
    for module_name in _EXPORT_MODULES:
        module = import_module(module_name)
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError(f"module 'app.agents' has no attribute {name!r}")
