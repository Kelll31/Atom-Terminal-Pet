"""Тесты подключения к модели: локальный сервер, адреса, список моделей."""

from ai import llm


def test_local_hosts_are_recognized():
    assert llm.is_local("http://127.0.0.1:1234/v1")
    assert llm.is_local("localhost:11434")
    assert not llm.is_local("https://api.deepseek.com/v1")
    assert not llm.is_local("")


def test_base_url_gets_scheme_and_v1_for_local_servers():
    # Адрес из окна LM Studio копируют без схемы и без «/v1»
    assert llm.normalize_base_url("127.0.0.1:1234") == "http://127.0.0.1:1234/v1"
    assert llm.normalize_base_url("http://localhost:1234/v1/") == "http://localhost:1234/v1"
    # Облачный адрес не трогаем — там путь может быть любым
    assert llm.normalize_base_url("https://api.deepseek.com/v1") == "https://api.deepseek.com/v1"
    assert llm.normalize_base_url("") == ""


def test_local_server_works_without_api_key():
    assert not llm.needs_api_key("", "http://127.0.0.1:1234/v1")
    assert llm.needs_api_key("", "")
    assert llm.needs_api_key("  ", "https://api.openai.com/v1")
    assert not llm.needs_api_key("sk-test", "https://api.openai.com/v1")


def test_cloud_key_is_not_sent_to_local_server():
    assert llm.effective_key("sk-secret", "http://127.0.0.1:1234/v1") == llm.LOCAL_KEY_PLACEHOLDER
    assert llm.effective_key("sk-secret", "https://api.openai.com/v1") == "sk-secret"


def test_api_root_drops_v1():
    assert llm.api_root("http://127.0.0.1:1234/v1") == "http://127.0.0.1:1234"


def test_embeddings_are_filtered_out():
    models = [
        {"id": "qwen3-8b", "type": "llm"},
        {"id": "text-embedding-nomic-embed-text-v1.5", "type": "embeddings"},
    ]
    assert [m["id"] for m in llm.chat_models(models)] == ["qwen3-8b"]


def test_model_type_is_guessed_without_lmstudio_rest():
    assert llm._model_entry({"id": "text-embedding-3-small"})["type"] == "embeddings"
    assert llm._model_entry({"id": "qwen2.5:7b"})["type"] == "llm"


def test_chat_model_builds_for_local_server_without_key():
    model = llm.build_chat_model(api_key="", base_url="127.0.0.1:1234", model="qwen3-8b")
    assert str(model.openai_api_base) == "http://127.0.0.1:1234/v1"
    assert model.model_name == "qwen3-8b"
    # Локальная модель грузится в память — таймаут должен быть щедрым
    assert model.request_timeout == llm.LOCAL_TIMEOUT_SEC
    assert model.max_retries == 0
