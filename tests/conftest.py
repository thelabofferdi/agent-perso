import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for k, v in {
        "RODIUM_API_KEY": "rd_sk_test", "TAVILY_API_KEY": "tvly-test", "OPENWEATHER_API_KEY": "w-test",
        "NOTION_TOKEN": "ntn_test", "NOTION_PARENT_PAGE_ID": "parent-1",
        "SMTP_USER": "bot@example.com", "SMTP_PASSWORD": "pw", "APP_ACCESS_CODE": "",
    }.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
