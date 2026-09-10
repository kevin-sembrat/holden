# Scoped to exactly what the edge-segment broker needs: read-only on its
# own segment's device credentials. Per the per-segment-broker decision,
# each broker instance gets its own AppRole bound to a policy scoped to
# only its segment's path -- this is the "edge" segment's policy; a
# "core" segment broker would get an analogous devices/data/core/* policy,
# never a shared devices/data/* grant. No component other than the broker
# for this segment is ever issued a token bound to this policy.
# Vault capabilities are default-deny: not granting create/update/delete
# here is sufficient to keep this AppRole read-only, without needing (and
# without risking a conflicting) explicit deny stanza on the same path.
path "devices/data/edge/*" {
  capabilities = ["read"]
}

path "devices/metadata/edge/*" {
  capabilities = ["read", "list"]
}
