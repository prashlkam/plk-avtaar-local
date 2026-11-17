import os
import tempfile

# Isolate test data before the app (and its DB singleton) is imported.
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="avtaar-test-")
os.environ.setdefault("OLLAMA_URL", "http://127.0.0.1:11434")
os.environ.setdefault("VOICESTUDIO_URL", "http://127.0.0.1:3900")
os.environ["FRONTEND_DIR"] = os.path.join(os.environ["DATA_DIR"], "no-ui")

import httpx  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_http_clients():
    """Each TestClient runs its own event loop; pooled connections must not leak across tests."""
    from app import deps

    for svc in (deps.voicestudio, deps.ollama):
        old = svc._client
        svc._client = httpx.AsyncClient(base_url=old.base_url, timeout=old.timeout, headers=old.headers)
    yield
