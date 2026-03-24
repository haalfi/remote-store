#!/usr/bin/env python3
"""Generate a short-lived GitHub App installation token for mobile/web sessions.

This script produces a 1-hour, repo-scoped token with minimal permissions —
safe to paste into a Claude Code web/mobile session where tokens unavoidably
enter the LLM context window.

One-time setup
--------------
1. Create a GitHub App at https://github.com/settings/apps/new

   Name:           remote-store-claude (or similar)
   Homepage URL:   https://github.com/haalfi/remote-store
   Webhook:        Uncheck "Active" (no webhook needed)

   Permissions (Repository):
     Contents:        Read
     Pull requests:   Read and write
     Metadata:        Read (auto-granted)

   Where can this app be installed?  "Only on this account"

2. After creation, note the **App ID** shown on the app settings page.

3. Generate a private key (app settings → Private keys → Generate).
   Save the .pem file somewhere safe (e.g., ~/.config/gh-app/remote-store.pem).

4. Install the app on your repo:
   App settings → Install App → select "haalfi/remote-store" only.
   Note the **Installation ID** from the URL after install
   (https://github.com/settings/installations/<INSTALLATION_ID>).

5. Set environment variables (add to your shell profile):

   export GH_APP_ID=<app-id>
   export GH_APP_INSTALLATION_ID=<installation-id>
   export GH_APP_PRIVATE_KEY_PATH=<path-to-pem-file>

Usage
-----
    python scripts/gh_app_token.py

    # Or pipe directly:
    export GITHUB_TOKEN=$(python scripts/gh_app_token.py)

The token expires in 1 hour, has access only to haalfi/remote-store,
and can only read contents + read/write pull requests.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# JWT generation (no external dependencies — uses stdlib only)
# ---------------------------------------------------------------------------


def _b64url(data: bytes) -> str:
    """Base64url-encode without padding."""
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _build_jwt(app_id: str, private_key_pem: str) -> str:
    """Create a RS256-signed JWT for GitHub App authentication.

    Uses the cryptography library if available, falls back to PyJWT.
    One of these is needed — both are common in Python environments.
    """
    now = int(time.time())
    payload = {
        "iat": now - 60,  # issued at (60s clock skew buffer)
        "exp": now + (10 * 60),  # expires in 10 minutes (max allowed)
        "iss": app_id,
    }

    # Try cryptography first (more commonly installed)
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        body = _b64url(json.dumps(payload).encode())
        unsigned = f"{header}.{body}".encode("ascii")

        private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
        signature = private_key.sign(unsigned, padding.PKCS1v15(), hashes.SHA256())  # type: ignore[union-attr]
        return f"{header}.{body}.{_b64url(signature)}"
    except ImportError:
        pass

    # Fallback to PyJWT
    try:
        import jwt

        return jwt.encode(payload, private_key_pem, algorithm="RS256")
    except ImportError:
        pass

    print(
        "Error: Need either 'cryptography' or 'PyJWT' installed.\n"
        "  pip install cryptography   (recommended)\n"
        "  pip install PyJWT",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------


def _api_request(url: str, token: str, method: str = "POST", data: dict | None = None) -> dict:
    """Make an authenticated GitHub API request."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data else None,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"GitHub API error ({e.code}): {body}", file=sys.stderr)
        sys.exit(1)


REPO_NAME = "remote-store"


def _get_installation_token(jwt_token: str, installation_id: str) -> str:
    """Exchange a JWT for a 1-hour installation access token.

    Explicitly scopes the token to a single repository so that installing
    the app on additional repos later doesn't silently widen access.
    """
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    result = _api_request(url, jwt_token, data={"repositories": [REPO_NAME]})
    return result["token"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    app_id = os.environ.get("GH_APP_ID")
    installation_id = os.environ.get("GH_APP_INSTALLATION_ID")
    key_path = os.environ.get("GH_APP_PRIVATE_KEY_PATH")

    missing = []
    if not app_id:
        missing.append("GH_APP_ID")
    if not installation_id:
        missing.append("GH_APP_INSTALLATION_ID")
    if not key_path:
        missing.append("GH_APP_PRIVATE_KEY_PATH")

    if missing:
        print(
            f"Error: Missing environment variables: {', '.join(missing)}\n"
            f"See docstring in this script for setup instructions.",
            file=sys.stderr,
        )
        sys.exit(1)

    assert key_path is not None  # for type checker
    key_path_expanded = os.path.expanduser(key_path)
    if not os.path.isfile(key_path_expanded):
        print(f"Error: Private key not found: {key_path_expanded}", file=sys.stderr)
        sys.exit(1)

    with open(key_path_expanded) as f:
        private_key_pem = f.read()

    # Step 1: Build JWT
    assert app_id is not None
    jwt_token = _build_jwt(app_id, private_key_pem)

    # Step 2: Exchange for installation token
    assert installation_id is not None
    token = _get_installation_token(jwt_token, installation_id)

    # Print just the token — easy to copy on mobile, pipe in scripts
    print(token)


if __name__ == "__main__":
    main()
