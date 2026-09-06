import pytest

import ash.nlu.context as context_module


@pytest.fixture(autouse=True)
def _reset_recent_context():
    """ash.nlu.context tracks last-opened-app/search/track as shared
    module state, touched by tests across several files (open_app,
    search, spotify, context, dispatcher) -- reset it before every test
    so none of them leak state into each other."""
    context_module._context = context_module._RecentContext()
    yield
