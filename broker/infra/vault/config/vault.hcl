# Local, air-gap-mode Vault for Holden secrets storage. No cloud auto-unseal,
# no telemetry/call-home, no dependency on live network services -- storage
# and unseal are both fully local. Only the broker's AppRole may read
# device-credential paths (enforced by policy, see broker-policy.hcl).

storage "file" {
  path = "/home/sembrat/holden_agent/broker/infra/vault/data"
}

listener "tcp" {
  address       = "127.0.0.1:8200"
  tls_cert_file = "/home/sembrat/holden_agent/broker/infra/vault/tls/vault.crt"
  tls_key_file  = "/home/sembrat/holden_agent/broker/infra/vault/tls/vault.key"
}

api_addr     = "https://127.0.0.1:8200"
disable_mlock = true  # dev host has no CAP_IPC_LOCK without root; revisit for a hardened deployment target
ui = false
