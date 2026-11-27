from types import SimpleNamespace

import httpx

from app.services import model_provider


class _FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeClient:
    def __init__(
        self,
        response: _FakeResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self._response = response
        self._error = error
        self.urls: list[str] = []

    def get(self, url: str, timeout: float | None = None) -> _FakeResponse:
        self.urls.append(url)
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


def _settings(base_url: str = "http://localhost:11434/v1") -> SimpleNamespace:
    return SimpleNamespace(ollama_base_url=base_url)


def test_cloud_provider_has_no_local_models() -> None:
    reachable, installed, message = model_provider.list_installed_models("openai")

    assert reachable is False
    assert installed == []
    assert "不支持" in message


def test_tags_url_strips_v1_suffix() -> None:
    assert (
        model_provider._tags_url("http://localhost:11434/v1")
        == "http://localhost:11434/api/tags"
    )
    assert (
        model_provider._tags_url("http://host.docker.internal:11434/v1/")
        == "http://host.docker.internal:11434/api/tags"
    )


def test_ollama_unreachable_is_reported(monkeypatch) -> None:
    client = _FakeClient(error=httpx.ConnectError("boom"))
    monkeypatch.setattr(model_provider, "_http_client", lambda: client)
    monkeypatch.setattr(model_provider, "get_settings", lambda: _settings())

    reachable, installed, message = model_provider.list_installed_models("ollama")

    assert reachable is False
    assert installed == []
    assert "无法连接" in message


def test_ollama_parses_installed_models(monkeypatch) -> None:
    client = _FakeClient(
        response=_FakeResponse({"models": [{"name": "qwen3:4b"}, {"model": "bge-m3"}]})
    )
    monkeypatch.setattr(model_provider, "_http_client", lambda: client)
    monkeypatch.setattr(model_provider, "get_settings", lambda: _settings())

    reachable, installed, message = model_provider.list_installed_models("ollama")

    assert reachable is True
    assert installed == ["qwen3:4b", "bge-m3"]
    assert message == ""
    assert client.urls == ["http://localhost:11434/api/tags"]


def test_ollama_bad_payload_is_reported(monkeypatch) -> None:
    client = _FakeClient(response=_FakeResponse(ValueError("bad json")))
    monkeypatch.setattr(model_provider, "_http_client", lambda: client)
    monkeypatch.setattr(model_provider, "get_settings", lambda: _settings())

    reachable, installed, message = model_provider.list_installed_models("ollama")

    assert reachable is False
    assert installed == []
    assert "无法解析" in message


def test_model_error_hint_points_to_pull_command() -> None:
    spec = model_provider.get_provider_spec("ollama")

    hint = model_provider._friendly_model_error(spec, "model 'bge-m3' not found")

    assert "ollama pull" in hint


def test_model_error_hint_leaves_other_errors_untouched() -> None:
    spec = model_provider.get_provider_spec("ollama")

    assert model_provider._friendly_model_error(spec, "401 invalid api key") == (
        "401 invalid api key"
    )
