"""``GraphAuth`` — the built-in MSAL-backed token provider.

Wraps MSAL with the two v1 flows (client-credentials and device-code) and
exposes the acquired bearer token through the token-provider protocol: a
``GraphAuth`` instance is itself a ``Callable[[], str]``, so
``GraphBackend(token_provider=GraphAuth(...))`` works directly.

``msal`` and ``platformdirs`` are imported lazily inside the methods that
need them so a caller supplying their own token-provider callable never
loads them.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from remote_store._config import Secret, _reveal

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

log = logging.getLogger("remote_store.aio.backends._graph")

# Client-credentials always requests the app's pre-consented application
# permissions via the ``.default`` scope; device-code requests delegated
# scopes the user consents to interactively.
#
# The device-code default is the *delegated* ``Files.ReadWrite`` (the
# signed-in user's own OneDrive) plus ``User.Read`` — validated live against a
# consumer account. The work/school app-only variants ``Files.ReadWrite.All`` /
# ``Sites.ReadWrite.All`` are NOT defaulted here: a personal Microsoft account
# cannot consent to them, so they would break the consumer device-code flow.
# Callers targeting SharePoint via delegated auth add ``Sites.ReadWrite.All``
# through ``scopes=``.
_DEFAULT_CC_SCOPES = ("https://graph.microsoft.com/.default",)
_DEFAULT_DEVICE_SCOPES = ("Files.ReadWrite", "User.Read")
_CACHE_FILENAME = "graph_token_cache.json"


class GraphAuth:
    """MSAL-backed token provider for ``GraphBackend``.

    Selects the OAuth flow from the supplied credentials: a ``client_secret``
    or ``client_certificate`` selects client-credentials (app-only); their
    absence selects device-code (interactive). The resulting bearer token is
    reachable through ``get_token()`` and through calling the instance directly.

    Args:
        tenant_id: Entra tenant id, or ``"consumers"`` / ``"common"`` /
            ``"organizations"`` for the device-code multi-tenant authorities.
        client_id: Application (client) id of the Entra app registration.
        client_secret: Client secret for client-credentials. Accepts a
            ``Secret`` and is masked in ``repr``.
        client_certificate: Certificate dict for client-credentials, as
            MSAL's ``client_credential`` mapping. Mutually exclusive with
            ``client_secret``.
        scopes: Override the default scope set. Client-credentials defaults
            to ``["https://graph.microsoft.com/.default"]``; device-code
            defaults to the delegated ``["Files.ReadWrite", "User.Read"]``
            (the signed-in user's OneDrive — consumer-compatible). Add
            ``Sites.ReadWrite.All`` for delegated SharePoint access.
        cache_path: Override the MSAL token-cache file location. Defaults to
            ``<user_config_dir("remote-store")>/graph_token_cache.json``.
        prompt_callback: Invoked with the MSAL device-flow dict on device-code
            login; defaults to printing ``flow["message"]``.

    Raises:
        ValueError: If ``tenant_id`` or ``client_id`` is empty, or if both
            ``client_secret`` and ``client_certificate`` are supplied.
    """

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        *,
        client_secret: str | Secret | None = None,
        client_certificate: dict[str, Any] | None = None,
        scopes: Sequence[str] | None = None,
        cache_path: str | None = None,
        prompt_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        if not tenant_id or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        if not client_id or not client_id.strip():
            raise ValueError("client_id must be a non-empty string")
        if client_secret is not None and client_certificate is not None:
            raise ValueError("Pass at most one of client_secret / client_certificate")

        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = _reveal(client_secret)
        self._client_certificate = client_certificate
        self._app_only = client_secret is not None or client_certificate is not None
        default_scopes = _DEFAULT_CC_SCOPES if self._app_only else _DEFAULT_DEVICE_SCOPES
        self._scopes = list(scopes) if scopes is not None else list(default_scopes)
        self._cache_path = cache_path
        self._prompt_callback = prompt_callback
        self._app: Any = None
        self._cache: Any = None

    @property
    def authority(self) -> str:
        """The MSAL authority URL derived from ``tenant_id``."""
        return f"https://login.microsoftonline.com/{self._tenant_id}"

    def _resolve_cache_path(self) -> str:
        if self._cache_path is not None:
            return self._cache_path
        import os  # noqa: PLC0415

        import platformdirs  # noqa: PLC0415 -- lazy: never loaded for user-supplied providers

        return os.path.join(platformdirs.user_config_dir("remote-store"), _CACHE_FILENAME)

    def _load_cache(self) -> Any:
        import os  # noqa: PLC0415

        from msal import SerializableTokenCache  # noqa: PLC0415

        cache = SerializableTokenCache()
        path = self._resolve_cache_path()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                cache.deserialize(fh.read())
        self._cache = cache
        return cache

    def _build_app(self) -> Any:
        if self._app is not None:
            return self._app
        import msal  # noqa: PLC0415

        cache = self._load_cache()
        if self._app_only:
            credential: Any = self._client_certificate if self._client_certificate is not None else self._client_secret
            self._app = msal.ConfidentialClientApplication(
                self._client_id, authority=self.authority, client_credential=credential, token_cache=cache
            )
        else:
            self._app = msal.PublicClientApplication(self._client_id, authority=self.authority, token_cache=cache)
        return self._app

    def _acquire(self) -> dict[str, Any]:
        app = self._build_app()
        if self._app_only:
            return app.acquire_token_for_client(scopes=self._scopes)  # type: ignore[no-any-return]
        # Device-code (GR-007): try the cache silently first, then fall back to
        # the interactive handshake (integration-only — it cannot be mocked at
        # the protocol layer).
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(self._scopes, account=accounts[0])
            if result and "access_token" in result:
                return result  # type: ignore[no-any-return]
        flow = app.initiate_device_flow(scopes=self._scopes)
        if "user_code" not in flow:
            raise ValueError(f"Failed to start device-code flow: {flow.get('error_description', flow)}")
        if self._prompt_callback is not None:
            self._prompt_callback(flow)
        else:
            print(flow["message"])  # noqa: T201 -- the device-code prompt is the user-facing instruction
        return app.acquire_token_by_device_flow(flow)  # type: ignore[no-any-return]

    def get_token(self) -> str:
        """Acquire (or silently refresh) a bearer token, flushing the cache.

        The token-provider callable the backend invokes. Re-invoking it after
        a ``401`` refreshes through MSAL's cache.

        Raises:
            PermissionError: If MSAL returns no token (auth failure); the
                ``error_description`` is included, never the secret.
        """
        result = self._acquire()
        token = result.get("access_token") if isinstance(result, dict) else None
        if not token:
            detail = (
                result.get("error_description", result.get("error", "unknown error"))
                if isinstance(result, dict)
                else "unknown error"
            )
            raise PermissionError(f"Graph token acquisition failed: {detail}")
        self.flush_cache()
        return str(token)

    def __call__(self) -> str:
        """Return a bearer token — makes the instance a token-provider callable."""
        return self.get_token()

    def flush_cache(self) -> None:
        """Persist the MSAL token cache to disk when it has changed.

        Called by ``get_token`` after every acquisition and by
        ``GraphBackend.close()``. Best-effort: a serialization or write
        failure is logged, not raised.
        """
        if self._cache is None or not self._cache.has_state_changed:
            return
        import os  # noqa: PLC0415

        path = self._resolve_cache_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self._cache.serialize())
        except OSError:
            log.warning("failed to persist Graph token cache to %s", path, exc_info=True)

    def __repr__(self) -> str:
        flow = "client_credentials" if self._app_only else "device_code"
        secret = _REPR_MASK if self._client_secret is not None else None
        cert = _REPR_MASK if self._client_certificate is not None else None
        return (
            f"GraphAuth(tenant_id={self._tenant_id!r}, client_id={self._client_id!r}, "
            f"flow={flow!r}, client_secret={secret!r}, client_certificate={cert!r})"
        )


_REPR_MASK = "***"
