"""
Minimal Vault client for the Execution Broker's credential layer.

Deliberately stdlib-only (no hvac/requests) so the broker's dependency
surface stays small and auditable on an air-gapped host. This module is
the *only* place in the repo permitted to hold a Vault AppRole
role_id/secret_id or call Vault's API -- the reasoning core, parser, and
audit writer must never import this module or reach Vault directly. That
boundary is enforced by Vault's own policy (a component without this
module's credentials has no token at all), not just by convention here.

Auth flow: AppRole login (role_id + secret_id) -> short-TTL Vault token ->
read one device credential by segment/device_id. The AppRole's Vault
policy (see broker/infra/vault/config/broker-policy.hcl) scopes reads to
exactly one segment's path -- this client does not add scoping itself,
Vault refuses out-of-scope reads regardless of what this code asks for.
"""

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class VaultConfig:
    addr: str
    ca_cert_path: str
    role_id_path: str
    secret_id_path: str


class VaultAuthError(Exception):
    pass


class VaultReadError(Exception):
    pass


def _read_stripped(path: str) -> str:
    with open(path, "r") as f:
        return f.read().strip()


def _request(cfg: VaultConfig, method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    url = f"{cfg.addr.rstrip('/')}/v1/{path.lstrip('/')}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("X-Vault-Token", token)
    if data is not None:
        req.add_header("Content-Type", "application/json")

    ctx = ssl.create_default_context(cafile=cfg.ca_cert_path)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise VaultReadError(f"{method} {path} -> HTTP {e.code}: {e.read().decode(errors='replace')}") from e


def approle_login(cfg: VaultConfig) -> str:
    """Exchange the broker's role_id/secret_id for a short-TTL Vault token. Never logs the secret_id."""
    role_id = _read_stripped(cfg.role_id_path)
    secret_id = _read_stripped(cfg.secret_id_path)
    try:
        resp = _request(cfg, "POST", "auth/approle/login", body={"role_id": role_id, "secret_id": secret_id})
    except VaultReadError as e:
        raise VaultAuthError(str(e)) from e
    return resp["auth"]["client_token"]


def read_device_credential(cfg: VaultConfig, token: str, segment: str, device_id: str) -> dict:
    """Read a device's service-account credential from KV v2. Raises VaultReadError if the
    AppRole's policy doesn't cover this path -- that's Vault enforcing the segment boundary,
    not a check performed here."""
    resp = _request(cfg, "GET", f"devices/data/{segment}/{device_id}", token=token)
    return resp["data"]["data"]


if __name__ == "__main__":
    cfg = VaultConfig(
        addr="https://127.0.0.1:8200",
        ca_cert_path="/home/sembrat/holden_agent/broker/infra/vault/tls/ca.crt",
        role_id_path="/home/sembrat/holden-tools/secrets/broker-edge/role_id",
        secret_id_path="/home/sembrat/holden-tools/secrets/broker-edge/secret_id",
    )

    token = approle_login(cfg)
    print(f"[ok] AppRole login succeeded, got a token (ttl-scoped, not shown)")

    creds = read_device_credential(cfg, token, "edge", "edge-sw-17")
    print(f"[ok] read devices/edge/edge-sw-17 -- username={creds['username']!r}, key present={'ssh_private_key' in creds}")

    print("[check] attempting an out-of-scope read (segment='core') with the same edge-scoped token...")
    try:
        read_device_credential(cfg, token, "core", "core-sw-04")
        print("[FAIL] out-of-scope read succeeded -- policy boundary is broken")
    except VaultReadError as e:
        print(f"[ok] out-of-scope read correctly denied by Vault policy: {e}")
