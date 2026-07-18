from __future__ import annotations

# Shared fakes (FakeGh, ScriptedEngine, ...) come from the core plugin — see
# my-things-core/docs/CONVENTIONS.md "Shared test fixtures". Don't copy
# fixture code into this file; only domain-specific helpers live here.
pytest_plugins = ("mythings.testing",)
