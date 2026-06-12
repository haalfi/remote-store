# Microsoft Graph Access Setup

Provision the credentials and a target drive for the Microsoft Graph
backend (OneDrive and SharePoint). This guide is for contributors who need
to run the live Graph test suite and for users who want to validate their
own app registration and drive resolution against `remote-store` before
production.

The audience is contributors and integrators standing up Graph access for
the first time. It covers the two authentication flows the backend
supports, how to register an Entra application for each, how to resolve an
opaque `drive_id`, and how to wire the result into your environment.

Unlike the [Azure HNS setup](azure-hns-setup.md), there is no resource to
create in an Azure subscription. OneDrive and SharePoint live in Microsoft
365 (Entra ID), not in an Azure subscription. The app registration is an
Entra directory object; the drive already exists in someone's OneDrive or
a SharePoint document library.

The shell snippets below are not executed in CI because they require
authenticated access and, in the app-only case, an admin-consented tenant.
Treat them as a recipe to copy line by line, not as exact reproducible
output.

## Which flow do you need?

Microsoft Graph offers two ways to obtain the bearer token the backend
attaches to every request. They map to two very different account types,
and the choice determines everything that follows.

| | Client-credentials (app-only) | Device-code (delegated) |
|---|---|---|
| Account type | Work/school tenant (Entra ID) | Personal Microsoft account, or work/school |
| Human at sign-in | No, non-interactive | Yes, browser login on first use |
| Secret | Client secret or certificate | None (public client) |
| Drive targets | SharePoint library, a user's OneDrive for Business | The signed-in user's OneDrive (`me`) |
| Best for | CI, daemons, services | Notebooks, CLIs, local development |

If you have a **work/school Microsoft 365 tenant** and admin rights, use
the [app-only path](#app-only-path-workschool-tenant) — it is
non-interactive and the natural fit for CI.

If you only have a **personal Microsoft account** (Outlook.com, a Microsoft
365 Family/Personal subscription, or consumer OneDrive), app-only auth is
not available to you at all — personal accounts have no tenant, no admin
consent, and no application permissions. Use the
[device-code path](#device-code-path-personal-account) instead.

> The device-code path below was walked end to end against a live consumer
> OneDrive while writing this guide. The app-only path is transcribed from
> Microsoft's documented flow and has **not** been validated in this
> repository's environment (no work/school tenant was available). A
> contributor with such a tenant should confirm the app-only steps and
> amend this guide.

## Prerequisites

- The [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
  (`az`) version 2.x, used here to create the app registration. You can do
  the same in the [Entra admin center](https://entra.microsoft.com) by
  hand if you prefer a portal.
- For app-only: a work/school tenant where you are a Global Administrator
  (or can have admin consent granted).
- For device-code: any personal or work Microsoft account that owns a
  OneDrive.

You register the application in any Entra tenant you control. For the
device-code path the registration tenant and the sign-in account need not
match — a multi-tenant app registered in your own tenant can sign in a
personal account from the `consumers` authority.

## Register the application

### Device-code path (personal account)

Register a public client that allows personal Microsoft accounts. No secret
is created.

```bash
az ad app create \
  --display-name "remote-store-graph-dev" \
  --sign-in-audience AzureADandPersonalMicrosoftAccount \
  --is-fallback-public-client true \
  --public-client-redirect-uris "https://login.microsoftonline.com/common/oauth2/nativeclient"
```

Read back the client id:

```bash
az ad app list \
  --display-name "remote-store-graph-dev" \
  --query "[0].{appId:appId, audience:signInAudience, publicClient:isFallbackPublicClient}" \
  -o json
```

`audience` must be `AzureADandPersonalMicrosoftAccount` and `publicClient`
must be `true`. The `appId` is your `GRAPH_CLIENT_ID`. There is no secret to
record — consent for the delegated `Files.ReadWrite` scope is granted by the
user at sign-in time.

### App-only path (work/school tenant)

Register a single-tenant confidential client, add a secret, grant
application permissions, and admin-consent them.

```bash
az ad app create \
  --display-name "remote-store-graph" \
  --sign-in-audience AzureADMyOrg
```

Add a client secret (record the returned `password` — it is shown once):

```bash
az ad app credential reset \
  --id <APP_ID> \
  --append \
  --display-name "graph-secret" \
  --years 1
```

Grant Microsoft Graph **application** permissions. The Graph resource id is
`00000003-0000-0000-c000-000000000000`; use the role id matching your drive
target:

- `Sites.ReadWrite.All` (`9492366f-7969-46a4-8d15-ed1a20078fff`) for
  SharePoint document libraries.
- `Files.ReadWrite.All` (`75359482-378d-4052-8f01-80520e7db3cd`) for a
  user's OneDrive for Business.

```bash
az ad app permission add \
  --id <APP_ID> \
  --api 00000003-0000-0000-c000-000000000000 \
  --api-permissions 9492366f-7969-46a4-8d15-ed1a20078fff=Role

az ad app permission admin-consent --id <APP_ID>
```

`admin-consent` requires Global Administrator rights. If you cannot run it,
have an admin open the consent URL:

```text
https://login.microsoftonline.com/<TENANT_ID>/adminconsent?client_id=<APP_ID>
```

Application permissions carry no user context, so app-only tokens cannot
reach `GET /me/drive`. They target a SharePoint library or a *named* user's
OneDrive for Business (`/users/{id}/drive`). A certificate may be used
instead of a secret; see the
[Microsoft client-credentials reference](https://learn.microsoft.com/entra/identity-platform/v2-oauth2-client-creds-grant-flow).

## Resolve the drive id

The Graph backend takes one opaque `drive_id`. Its public helper
`GraphUtils.resolve_drive_id(...)` accepts three target shapes and returns
that id:

- **`"me"`** — the signed-in user's OneDrive, via `GET /me/drive`.
  Delegated (device-code) only.
- **A SharePoint site URL** (optionally with a library name) — via
  `GET /sites/{id}/drive` or `GET /sites/{id}/drives`. Works with app-only.
- **A Teams channel** `{team_id, channel_id}` mapping — via the channel's
  `filesFolder`. Works with app-only.

With the backend installed, resolving and capturing the id is three lines:

```python
# pip install "remote-store[graph]"
from remote_store.aio import GraphAuth, GraphUtils

auth = GraphAuth(tenant_id="consumers", client_id="<GRAPH_CLIENT_ID>")
print("GRAPH_DRIVE_ID=" + GraphUtils.resolve_drive_id("me", token_provider=auth))
```

The first run completes a device-code sign-in in the terminal; `GraphAuth`
caches the token, so later runs are non-interactive. If you prefer to
validate the app registration without installing anything, the hand-rolled
verification snippet below does the same with raw `msal` + `httpx`.

## Verify and capture the drive id (device-code)

An alternative to the `GraphUtils` route above: this snippet completes a
device-code sign-in and reads back your drive id using `msal` and `httpx`
directly (the libraries the built-in `GraphAuth` helper wraps), so it works
without the `graph` extra installed — useful for verifying the app
registration in isolation. It is hand-written rather than sourced from
`examples/snippets/` because it needs real interactive credentials and
cannot run in CI.

```python
import json, os, sys
import httpx, msal

CLIENT_ID = "<GRAPH_CLIENT_ID>"
AUTHORITY = "https://login.microsoftonline.com/consumers"  # personal accounts
SCOPES = ["Files.ReadWrite", "User.Read"]
CACHE_PATH = "graph_token_cache.json"

cache = msal.SerializableTokenCache()
if os.path.exists(CACHE_PATH):
    cache.deserialize(open(CACHE_PATH, encoding="utf-8").read())

app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)

result = None
if app.get_accounts():
    result = app.acquire_token_silent(SCOPES, account=app.get_accounts()[0])
if not result:
    flow = app.initiate_device_flow(scopes=SCOPES)
    print(flow["message"], flush=True)        # open the URL, enter the code
    result = app.acquire_token_by_device_flow(flow)

if "access_token" not in result:
    sys.exit(result.get("error_description", "auth failed"))
if cache.has_state_changed:
    open(CACHE_PATH, "w", encoding="utf-8").write(cache.serialize())

headers = {"Authorization": f"Bearer {result['access_token']}"}
drive = httpx.get(
    "https://graph.microsoft.com/v1.0/me/drive",
    params={"$select": "id,driveType,owner,webUrl"},
    headers=headers,
    timeout=30,
).json()
print("driveType:", drive["driveType"])       # 'personal' for consumer OneDrive
print("GRAPH_DRIVE_ID=" + drive["id"])
```

Sign in with the account that owns the target OneDrive. The `consumers`
authority rejects work/school accounts, which keeps a personal-account run
unambiguous. The token cache it writes makes the second run non-interactive
— the same property the live test fixture relies on.

For a SharePoint or Teams target (app-only), swap the authority for your
tenant, acquire a token with `acquire_token_for_client`, and call
`GET /sites/root` or `GET /sites/{id}/drives` instead of `/me/drive`.

## Wire credentials into the environment

`remote-store` live Graph tests read configuration from environment
variables, loaded from your project `.env`. The opt-in flag is
`RS_TEST_LIVE_GRAPH=1`; the remaining variables differ by flow.

Device-code (personal account) — no secret:

```bash
RS_TEST_LIVE_GRAPH=1
GRAPH_CLIENT_ID=<your app client id>
GRAPH_TENANT_ID=consumers
GRAPH_DRIVE_ID=<id from the verification snippet>
```

App-only (work/school tenant) — with secret:

```bash
RS_TEST_LIVE_GRAPH=1
GRAPH_TENANT_ID=<your tenant GUID>
GRAPH_CLIENT_ID=<your app client id>
GRAPH_CLIENT_SECRET=<the secret from az ad app credential reset>
GRAPH_DRIVE_ID=<id resolved from your SharePoint or OneDrive target>
```

`.env` is gitignored. Never commit `GRAPH_CLIENT_SECRET` or the MSAL token
cache (it holds a refresh token).

The built-in `GraphAuth` helper persists its MSAL cache under your user
config directory (`platformdirs.user_config_dir("remote-store")`). The
hand-rolled verification snippet above uses a local cache file instead, to
stay self-contained.

## Troubleshooting

**`AADSTS50076` on app creation or sign-in.** Per-resource MFA. Sign in to
the specific tenant: `az login --tenant <TENANT_ID>`.

**`AADSTS65001` (consent required).** The app-only permissions were added
but not admin-consented. Run `az ad app permission admin-consent` or open
the admin-consent URL above.

**`AADSTS700016` / `AADSTS50020` on device-code sign-in.** The account type
does not match the app audience — e.g. signing a personal account into a
single-tenant app, or vice versa. Confirm the registration used
`AzureADandPersonalMicrosoftAccount` and the authority is `consumers`.

**`AADSTS7000215` (invalid client secret).** The secret expired or was
mistyped. Re-run `az ad app credential reset` and update `.env`.

**`Tenant does not have a SPO license`** on `GET /me/drive` or
`GET /sites/root`. The tenant has no SharePoint Online plan, so no drives
exist. This is expected for a bare Azure subscription with no Microsoft 365
licenses; use a personal account (device-code) or add an M365 license to
the tenant.

## Cleanup

Delete the app registration when you are done:

```bash
az ad app delete --id <APP_ID>
```

There is nothing to delete on the drive side — no resource was provisioned;
you used an existing OneDrive or SharePoint library. To revoke a personal
account's delegated consent, remove the app from
[your account's app permissions](https://account.live.com/consent/Manage).

## See also

- [Azure HNS setup](azure-hns-setup.md) — the analogous runbook for a real
  ADLS Gen2 account
- [Choosing a backend](../choosing-a-backend.md) — decision guide with
  trade-offs
- [Capabilities matrix](../../reference/capabilities-matrix.md) — full
  backend × capability table
- [`AsyncStore` API reference](../../reference/api/aio.md) — the async
  surface the Graph backend implements
- [Microsoft Graph authentication overview](https://learn.microsoft.com/graph/auth/auth-concepts)
- [OAuth 2.0 device-code flow](https://learn.microsoft.com/entra/identity-platform/v2-oauth2-device-code)
