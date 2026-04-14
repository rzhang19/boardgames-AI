import os
import pytest

from bot import is_authorized, load_config, parse_target, get_service


class TestIsAuthorized:
    def test_authorized_user_returns_true(self):
        import bot
        bot.AUTHORIZED_IDS = {12345, 67890}
        assert is_authorized(12345) is True

    def test_unauthorized_user_returns_false(self):
        import bot
        bot.AUTHORIZED_IDS = {12345, 67890}
        assert is_authorized(99999) is False

    def test_empty_authorized_set_returns_false(self):
        import bot
        bot.AUTHORIZED_IDS = set()
        assert is_authorized(12345) is False


class TestParseTarget:
    def test_no_args_defaults_to_production(self):
        target, remaining = parse_target(None)
        assert target == "production"
        assert remaining == []

    def test_empty_args_defaults_to_production(self):
        target, remaining = parse_target([])
        assert target == "production"
        assert remaining == []

    def test_staging_keyword(self):
        target, remaining = parse_target(["staging"])
        assert target == "staging"
        assert remaining == []

    def test_stg_keyword(self):
        target, remaining = parse_target(["stg"])
        assert target == "staging"
        assert remaining == []

    def test_staging_with_sha(self):
        target, remaining = parse_target(["staging", "abc1234"])
        assert target == "staging"
        assert remaining == ["abc1234"]

    def test_sha_without_target_defaults_production(self):
        target, remaining = parse_target(["abc1234"])
        assert target == "production"
        assert remaining == ["abc1234"]

    def test_staging_with_list(self):
        target, remaining = parse_target(["staging", "list"])
        assert target == "staging"
        assert remaining == ["list"]


class TestGetService:
    def test_production_returns_web(self):
        assert get_service("production") == "web"

    def test_staging_returns_staging_web(self):
        assert get_service("staging") == "staging-web"


class TestLoadConfig:
    def test_loads_bot_token(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-token-123"
        os.environ["TELEGRAM_ALLOWED_USER_IDS"] = "111,222"
        os.environ["PROJECT_DIR"] = "/test/dir"
        load_config()
        import bot
        assert bot.BOT_TOKEN == "test-token-123"
        assert bot.AUTHORIZED_IDS == {111, 222}
        assert bot.PROJECT_DIR == "/test/dir"
        del os.environ["TELEGRAM_BOT_TOKEN"]
        del os.environ["TELEGRAM_ALLOWED_USER_IDS"]
        del os.environ["PROJECT_DIR"]

    def test_empty_user_ids(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-token"
        os.environ["TELEGRAM_ALLOWED_USER_IDS"] = ""
        load_config()
        import bot
        assert bot.AUTHORIZED_IDS == set()
        del os.environ["TELEGRAM_BOT_TOKEN"]
        del os.environ["TELEGRAM_ALLOWED_USER_IDS"]

    def test_skips_non_numeric_user_ids(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-token"
        os.environ["TELEGRAM_ALLOWED_USER_IDS"] = "123,abc,456"
        load_config()
        import bot
        assert bot.AUTHORIZED_IDS == {123, 456}
        del os.environ["TELEGRAM_BOT_TOKEN"]
        del os.environ["TELEGRAM_ALLOWED_USER_IDS"]
