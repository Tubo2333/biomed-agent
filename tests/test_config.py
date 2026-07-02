# tests/test_config.py — Config loading tests


from src.config import config


class TestConfig:
    """Config loaded from config.yaml with dot-attribute access."""

    def test_llm_section(self):
        assert config.llm.model == "deepseek-v4-pro"
        assert config.llm.temperature == 0.3

    def test_rag_section(self):
        assert config.rag.max_search_rounds == 3
        assert config.rag.token_budget == 15000

    def test_storage_section(self):
        assert "biomed-agent" in config.storage.db_path

    def test_api_section(self):
        assert config.api.port == 8000

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("BIOMED_API_PORT", "9999")
        # Reload to pick up env var
        import importlib
        import src.config as cfg_mod
        importlib.reload(cfg_mod)
        assert cfg_mod.config.api.port == 9999
        # Restore
        monkeypatch.delenv("BIOMED_API_PORT")
        importlib.reload(cfg_mod)
