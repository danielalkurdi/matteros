from __future__ import annotations

import json
import time
from pathlib import Path

from matteros.connectors.ms_graph_auth import MicrosoftGraphTokenManager


def test_get_access_token_uses_valid_cached_token(tmp_path: Path) -> None:
    cache = tmp_path / "ms_graph_token.json"
    manager = MicrosoftGraphTokenManager(
        cache_path=cache,
        tenant_id="common",
        client_id="client-id",
        scopes="offline_access User.Read",
    )

    manager.save_cache(
        {
            "access_token": "cached-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "scope": "offline_access User.Read",
            "token_type": "Bearer",
        }
    )

    token = manager.get_access_token(interactive=False)
    assert token == "cached-token"


def test_get_access_token_refreshes_expired_token(tmp_path: Path) -> None:
    cache = tmp_path / "ms_graph_token.json"
    manager = MicrosoftGraphTokenManager(
        cache_path=cache,
        tenant_id="common",
        client_id="client-id",
        scopes="offline_access User.Read",
    )

    cache.write_text(
        json.dumps(
            {
                "provider": "microsoft_graph",
                "tenant_id": "common",
                "client_id": "client-id",
                "scope": "offline_access User.Read",
                "token_type": "Bearer",
                "access_token": "old-token",
                "refresh_token": "refresh-token",
                "expires_at": int(time.time()) - 10,
                "obtained_at": int(time.time()) - 100,
            }
        ),
        encoding="utf-8",
    )

    def fake_post_form(url: str, form: dict[str, str], allow_oauth_errors: bool = False):
        assert form["grant_type"] == "refresh_token"
        return {
            "access_token": "new-token",
            "refresh_token": "new-refresh-token",
            "expires_in": 1800,
            "scope": "offline_access User.Read",
            "token_type": "Bearer",
        }

    manager._post_form = fake_post_form  # type: ignore[method-assign]

    token = manager.get_access_token(interactive=False)
    assert token == "new-token"

    cached = manager.load_cache()
    assert cached is not None
    assert cached["access_token"] == "new-token"


def test_cache_status_reports_missing_when_no_file(tmp_path: Path) -> None:
    manager = MicrosoftGraphTokenManager(
        cache_path=tmp_path / "missing.json",
        tenant_id="common",
        client_id="client-id",
        scopes="offline_access User.Read",
    )
    status = manager.cache_status()
    assert status["status"] == "missing"
