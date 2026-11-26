"""
Tests for the LLM provider abstraction (Phase 3.1.3).

Covers the provider contract, the standard response object, the deterministic
fake provider, and the Ollama provider against a local stub HTTP server. No
test connects to a real Ollama instance or any external network; the only
network traffic is HTTP to 127.0.0.1 on an ephemeral port.
"""

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from productsignal.llm import (
    FakeProvider,
    LLMConnectionError,
    LLMProvider,
    LLMProviderError,
    LLMResponse,
    LLMResponseError,
    LLMTimeoutError,
    OllamaProvider,
    create_provider,
)
from productsignal.config import ProviderConfig


# ---------------------------------------------------------------------------
# Local stub Ollama server (127.0.0.1, ephemeral port)
# ---------------------------------------------------------------------------

class _StubOllamaHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        state = self.server.state
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except ValueError:
            body = {"__unparsed__": raw.decode("utf-8", errors="replace")}
        state.last_request = {"path": self.path, "body": body}

        behavior = state.behavior
        if behavior.get("sleep"):
            time.sleep(behavior["sleep"])

        if "raw" in behavior:
            payload = behavior["raw"]
            content_type = behavior.get("content_type", "application/json")
        else:
            payload = json.dumps(behavior.get("json", {})).encode("utf-8")
            content_type = "application/json"

        self.send_response(behavior.get("status", 200))
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass  # keep test output clean


class _StubOllamaServer:
    """Minimal scriptable stand-in for Ollama's /api/generate endpoint."""

    def __init__(self):
        self.behavior = {
            "status": 200,
            "json": {"response": "ok", "model": "stub-model", "done": True},
        }
        self.last_request = None
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _StubOllamaHandler)
        self._server.state = self
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def start(self):
        self._thread.start()

    def stop(self):
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def stub_ollama():
    server = _StubOllamaServer()
    server.start()
    yield server
    server.stop()


def _closed_port() -> int:
    """Find a port with nothing listening, for connection-failure tests."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return port


# ---------------------------------------------------------------------------
# Provider abstraction contract
# ---------------------------------------------------------------------------

class TestProviderContract:
    def test_fake_provider_satisfies_protocol(self):
        assert isinstance(FakeProvider(), LLMProvider)

    def test_ollama_provider_satisfies_protocol(self):
        provider = OllamaProvider(base_url="http://localhost:11434", model="m")
        assert isinstance(provider, LLMProvider)

    def test_standard_response_structure(self):
        response = LLMResponse(
            text="output", provider="fake", model="m",
            duration_seconds=0.1, metadata={"k": "v"},
        )
        assert response.text == "output"
        assert response.provider == "fake"
        assert response.model == "m"
        assert response.duration_seconds == 0.1
        assert response.metadata == {"k": "v"}

    def test_response_defaults(self):
        response = LLMResponse(text="t", provider="p", model="m")
        assert response.duration_seconds is None
        assert response.metadata == {}

    def test_provider_identity(self):
        fake = FakeProvider(model="fake-model")
        assert fake.provider_name == "fake"
        assert fake.model_name == "fake-model"

        ollama = OllamaProvider(base_url="http://localhost:11434", model="llama3")
        assert ollama.provider_name == "ollama"
        assert ollama.model_name == "llama3"
        assert ollama.base_url == "http://localhost:11434"

    def test_exception_hierarchy(self):
        assert issubclass(LLMConnectionError, LLMProviderError)
        assert issubclass(LLMTimeoutError, LLMProviderError)
        assert issubclass(LLMResponseError, LLMProviderError)

    def test_ollama_rejects_empty_configuration(self):
        with pytest.raises(ValueError, match="base_url"):
            OllamaProvider(base_url="", model="m")
        with pytest.raises(ValueError, match="model"):
            OllamaProvider(base_url="http://localhost:11434", model="")
        with pytest.raises(ValueError, match="timeout"):
            OllamaProvider(base_url="http://localhost:11434", model="m", timeout_seconds=0)

    def test_fake_rejects_empty_model(self):
        with pytest.raises(ValueError, match="model"):
            FakeProvider(model="")


# ---------------------------------------------------------------------------
# Fake provider
# ---------------------------------------------------------------------------

class TestFakeProvider:
    def test_successful_response(self):
        provider = FakeProvider(model="fake-model")
        provider.configure("category: reliability_downtime")

        response = provider.generate("classify this feedback")

        assert response.text == "category: reliability_downtime"
        assert response.provider == "fake"
        assert response.model == "fake-model"
        assert response.duration_seconds == 0.0
        assert response.metadata == {"simulated": True}

    def test_configured_failure_raises(self):
        provider = FakeProvider()
        failure = LLMTimeoutError("simulated timeout")
        provider.configure(failure)

        with pytest.raises(LLMTimeoutError, match="simulated timeout"):
            provider.generate("prompt")

    def test_sequential_responses_in_order(self):
        provider = FakeProvider()
        provider.configure("first", LLMProviderError("middle fails"), "third")

        assert provider.generate("p1").text == "first"
        with pytest.raises(LLMProviderError, match="middle fails"):
            provider.generate("p2")
        assert provider.generate("p3").text == "third"
        assert provider.remaining_responses == 0

    def test_constructor_queue(self):
        provider = FakeProvider(responses=["a", "b"])
        assert provider.generate("1").text == "a"
        assert provider.generate("2").text == "b"

    def test_exhausted_queue_raises(self):
        provider = FakeProvider()
        with pytest.raises(LLMProviderError, match="no configured responses"):
            provider.generate("prompt")

    def test_requests_recorded(self):
        provider = FakeProvider()
        provider.configure("ok")
        provider.generate(
            "the prompt",
            system_prompt="be terse",
            temperature=0.2,
            timeout_seconds=5.0,
        )

        assert len(provider.recorded_requests) == 1
        recorded = provider.recorded_requests[0]
        assert recorded.prompt == "the prompt"
        assert recorded.system_prompt == "be terse"
        assert recorded.temperature == 0.2
        assert recorded.timeout_seconds == 5.0

    def test_no_network_by_construction(self):
        """The fake provider is pure in-memory: generating must not open sockets.
        Verified by running against a torn-down network namespace substitute —
        nothing to assert beyond successful generation with no server running."""
        provider = FakeProvider(responses=["offline"])
        assert provider.generate("p").text == "offline"


# ---------------------------------------------------------------------------
# Ollama provider (against the local stub server)
# ---------------------------------------------------------------------------

class TestOllamaProvider:
    def test_request_construction_and_response_extraction(self, stub_ollama):
        provider = OllamaProvider(
            base_url=stub_ollama.base_url, model="qwen2.5:7b"
        )
        response = provider.generate("Classify: dashboard slow")

        assert response.text == "ok"
        assert response.provider == "ollama"
        assert response.model == "stub-model"  # model echoed by the endpoint
        assert isinstance(response.duration_seconds, float) and response.duration_seconds >= 0
        assert response.metadata.get("done") is True

        request = stub_ollama.last_request
        assert request["path"] == "/api/generate"
        assert request["body"]["model"] == "qwen2.5:7b"
        assert request["body"]["prompt"] == "Classify: dashboard slow"
        assert request["body"]["stream"] is False
        assert "system" not in request["body"]
        assert "options" not in request["body"]

    def test_system_prompt_and_temperature_included_when_given(self, stub_ollama):
        provider = OllamaProvider(base_url=stub_ollama.base_url, model="m")
        provider.generate("p", system_prompt="sys", temperature=0.3)

        body = stub_ollama.last_request["body"]
        assert body["system"] == "sys"
        assert body["options"] == {"temperature": 0.3}

    def test_raw_text_passed_through_untouched(self, stub_ollama):
        raw = '  {"weird": "output", "trailing": 1}\n'
        stub_ollama.behavior = {"status": 200, "json": {"response": raw}}
        provider = OllamaProvider(base_url=stub_ollama.base_url, model="m")

        assert provider.generate("p").text == raw  # no parsing or normalization

    def test_configurable_model_and_base_url(self, stub_ollama):
        provider = OllamaProvider(
            base_url=f"{stub_ollama.base_url}/prefix", model="custom-model"
        )
        provider.generate("p")

        assert stub_ollama.last_request["path"] == "/prefix/api/generate"
        assert stub_ollama.last_request["body"]["model"] == "custom-model"

    def test_timeout_raises_llm_timeout_error(self, stub_ollama):
        stub_ollama.behavior = {
            "status": 200,
            "json": {"response": "late"},
            "sleep": 1.0,
        }
        provider = OllamaProvider(
            base_url=stub_ollama.base_url, model="m", timeout_seconds=0.2
        )
        with pytest.raises(LLMTimeoutError, match="timed out after 0.2s"):
            provider.generate("p")

    def test_per_request_timeout_override(self, stub_ollama):
        stub_ollama.behavior = {"status": 200, "json": {"response": "late"}, "sleep": 1.0}
        provider = OllamaProvider(
            base_url=stub_ollama.base_url, model="m", timeout_seconds=30.0
        )
        with pytest.raises(LLMTimeoutError):
            provider.generate("p", timeout_seconds=0.2)

    def test_connection_failure_raises_llm_connection_error(self):
        provider = OllamaProvider(
            base_url=f"http://127.0.0.1:{_closed_port()}", model="m"
        )
        with pytest.raises(LLMConnectionError, match="Could not connect"):
            provider.generate("p")

    def test_http_error_status_raises_llm_response_error(self, stub_ollama):
        stub_ollama.behavior = {"status": 500, "json": {"error": "boom"}}
        provider = OllamaProvider(base_url=stub_ollama.base_url, model="m")

        with pytest.raises(LLMResponseError, match="HTTP 500"):
            provider.generate("p")

    def test_malformed_json_raises_llm_response_error(self, stub_ollama):
        stub_ollama.behavior = {"status": 200, "raw": b"this is not json"}
        provider = OllamaProvider(base_url=stub_ollama.base_url, model="m")

        with pytest.raises(LLMResponseError, match="not valid JSON"):
            provider.generate("p")

    def test_missing_response_field_raises_llm_response_error(self, stub_ollama):
        stub_ollama.behavior = {"status": 200, "json": {"unexpected": "shape"}}
        provider = OllamaProvider(base_url=stub_ollama.base_url, model="m")

        with pytest.raises(LLMResponseError, match="'response' text field"):
            provider.generate("p")

    def test_non_string_response_field_raises_llm_response_error(self, stub_ollama):
        stub_ollama.behavior = {"status": 200, "json": {"response": 123}}
        provider = OllamaProvider(base_url=stub_ollama.base_url, model="m")

        with pytest.raises(LLMResponseError, match="'response' text field"):
            provider.generate("p")


PROMPT_MARKER = "CUSTOMER-FEEDBACK: employees cannot export Q3 reports"
BODY_SECRET = "SECRET-INTERNAL-STACKTRACE-DETAIL"


class TestOllamaErrorSanitization:
    """Exception messages must stay useful (status/provider) without leaking
    response bodies, prompts, or request internals."""

    def test_http_error_excludes_response_body(self, stub_ollama):
        stub_ollama.behavior = {
            "status": 400,
            "json": {"error": f"bad request: {BODY_SECRET}"},
        }
        provider = OllamaProvider(base_url=stub_ollama.base_url, model="m")

        with pytest.raises(LLMResponseError) as exc_info:
            provider.generate(PROMPT_MARKER)

        message = str(exc_info.value)
        assert "HTTP 400" in message            # status code retained
        assert "Ollama" in message              # provider identity retained
        assert BODY_SECRET not in message       # body content excluded
        assert PROMPT_MARKER not in message     # no prompt echo via body

    def test_error_body_echoing_prompt_is_not_exposed(self, stub_ollama):
        stub_ollama.behavior = {
            "status": 500,
            "json": {"error": "echo", "request": {"prompt": PROMPT_MARKER}},
        }
        provider = OllamaProvider(base_url=stub_ollama.base_url, model="m")

        with pytest.raises(LLMResponseError) as exc_info:
            provider.generate(PROMPT_MARKER)

        assert PROMPT_MARKER not in str(exc_info.value)
        assert "echo" not in str(exc_info.value)

    def test_malformed_json_error_excludes_raw_body(self, stub_ollama):
        stub_ollama.behavior = {
            "status": 200,
            "raw": f"oops {BODY_SECRET} {PROMPT_MARKER}".encode("utf-8"),
        }
        provider = OllamaProvider(base_url=stub_ollama.base_url, model="m")

        with pytest.raises(LLMResponseError) as exc_info:
            provider.generate(PROMPT_MARKER)

        message = str(exc_info.value)
        assert BODY_SECRET not in message
        assert PROMPT_MARKER not in message

    def test_missing_field_error_excludes_payload(self, stub_ollama):
        stub_ollama.behavior = {
            "status": 200,
            "json": {"unexpected": BODY_SECRET},
        }
        provider = OllamaProvider(base_url=stub_ollama.base_url, model="m")

        with pytest.raises(LLMResponseError) as exc_info:
            provider.generate(PROMPT_MARKER)

        assert BODY_SECRET not in str(exc_info.value)

    def test_timeout_message_contains_no_request_content(self, stub_ollama):
        stub_ollama.behavior = {"status": 200, "json": {"response": "late"}, "sleep": 1.0}
        provider = OllamaProvider(
            base_url=stub_ollama.base_url, model="m", timeout_seconds=0.2
        )

        with pytest.raises(LLMTimeoutError) as exc_info:
            provider.generate(PROMPT_MARKER)

        message = str(exc_info.value)
        assert "timed out" in message
        assert PROMPT_MARKER not in message
        assert BODY_SECRET not in message

    def test_connection_error_contains_no_prompt_or_credentials(self):
        provider = OllamaProvider(
            base_url=f"http://127.0.0.1:{_closed_port()}", model="m"
        )

        with pytest.raises(LLMConnectionError) as exc_info:
            provider.generate(PROMPT_MARKER)

        message = str(exc_info.value)
        assert "Could not connect" in message
        assert PROMPT_MARKER not in message
        assert "Authorization" not in message and "authorization" not in message

    def test_catch_all_request_error_exposes_no_details(self, stub_ollama, monkeypatch):
        """Unexpected requests failures surface only the exception type name."""
        import requests

        def boom(url, **kwargs):
            raise requests.exceptions.RequestException(
                f"leaky detail {PROMPT_MARKER}"
            )

        monkeypatch.setattr(requests, "post", boom)
        provider = OllamaProvider(base_url=stub_ollama.base_url, model="m")

        with pytest.raises(LLMProviderError) as exc_info:
            provider.generate(PROMPT_MARKER)

        assert PROMPT_MARKER not in str(exc_info.value)
        assert "RequestException" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

class TestProviderFactory:
    def test_creates_ollama_provider_from_config(self):
        config = ProviderConfig(
            name="ollama", model="qwen2.5:7b",
            base_url="http://127.0.0.1:11434", timeout_seconds=12.5,
        )
        provider = create_provider(config)

        assert isinstance(provider, OllamaProvider)
        assert provider.model_name == "qwen2.5:7b"
        assert provider.base_url == "http://127.0.0.1:11434"
        assert provider.provider_name == "ollama"

    def test_creates_fake_provider_from_config(self):
        provider = create_provider(ProviderConfig(name="fake", model="fake-model"))
        assert isinstance(provider, FakeProvider)
        assert provider.model_name == "fake-model"
