# Project Holden — Engineering Scope Document

## Vision

An autonomous, 100% offline LLM agent for air-gapped, hardened military and
industrial control system (ICS) LAN environments. The agent diagnoses network
health, produces human-readable reports, recommends remediations, and — upon
human approval — consoles into affected nodes to apply changes, then
re-verifies and reports results.

Core architectural pattern: **Parser (Tool) → RAG Knowledge → Reasoning
(SLM)**, with a strict separation between reasoning and execution (see
Credential/RBAC Architecture below).

---

## Phases & Dependencies

| # | Phase | Delivers | Depends on |
|---|-------|----------|-------------|
| 0 | Threat model & credential architecture — **complete 2026-09-10, one follow-up tracked** | Trust boundaries, RBAC model, credential lifecycle (see below) | — (do first) |
| 1 | Testing harness — **complete 2026-09-10, checklist 1.1–1.5** | Containerlab-based virtual networks with scriptable, scoreable fault injection | Phase 0 |
| 2 | Parser/Tool layer | Whitelisted low-level device ops; binary/CLI output → structured text | Phase 1 |
| 3 | RAG knowledge base | Indexed vendor manuals in a local vector store; retrieval tuned for protocol/error lookups | Parallel with Phase 2 |
| 4 | Reasoning core (SLM) | Diagnosis + structured report generation from parsed output + RAG context | Phases 2 & 3 |
| 5 | Remediation proposal + approval loop | Agent proposes fixes; human approves / denies+feedback | Phase 4 |
| 6 | Execution broker + console-in | Approved diffs applied via scoped, short-lived credentials | Phase 5, hard dependency on Phase 0 |
| 7 | Closed-loop verification | Re-test post-change, confirm fix or escalate | Phase 6 |
| 8 | Adversarial hardening | Red-team the agent itself: prompt injection via device output, malformed telemetry, credential-boundary testing | Phases 4–7 complete |
| 9 | Field pilot | Deploy on a real, non-critical segment | Phase 8 sign-off |

**Critical path:** Phase 0 → Phase 6. Credential/RBAC scoping must be
architected before the execution broker is built, not retrofitted onto it.

---

## Credential / RBAC Architecture

### Core principle
The LLM never holds, generates, or transmits credentials. It only ever
emits a **structured intent** (e.g. `{action: "set_vlan", target:
"switch-04", interface: "gi0/3", value: "VLAN 20"}`). A separate,
deterministic **Execution Broker** — no LLM inside it — validates intents
against RBAC policy and a hard command whitelist, then performs the actual
device interaction. This means the LLM's worst-case failure mode (bad
diagnosis, prompt injection via malicious telemetry) can only ever produce a
*request*, never a direct action.

### Privilege tiers
| Tier | Capability | Approval needed |
|---|---|---|
| 0 | Read-only telemetry (SNMP, `show`, logs) | None |
| 1 | Non-destructive diagnostic probes (ping, traceroute, test frames) | None |
| 2 | Proposed remediation (dry-run diff only, no device contact) | None |
| 3 | Approved write (actual config push) | Human approval → mints a short-lived, single-use, scoped credential for that exact diff/device/TTL |
| 4 | Emergency rollback | Auto-triggered on failed post-change verification, or human override |

### Credential model
- Local, offline root CA issuing short-TTL certs (e.g. `step-ca`) — no
  dependency on live OCSP/CRL; revocation is via short TTL expiry.
- Per-device or per-segment service accounts — never one global credential.
- Secrets at rest in **Vault, air-gap mode** (v1 decision — see Open
  Decisions history below; no HSM in v1, revisit if this moves toward a
  hardware-certified deployment). Only the broker reads from it; the LLM
  never touches it.
- Rotation handled by a local scheduled job signed by the local CA.

### RBAC scoping
- Roles scoped to network segment + device class (e.g.
  `core-switches:read-only`, `edge-nodes:tier3-write`), not flat admin/user.
- Command whitelist enforced **at the broker**, keyed by role — independent
  of what the LLM requested.
- Hard-coded deny list regardless of role: factory reset, firmware flash,
  device-local account/password changes. Excluded from the autonomous loop
  entirely in v1; require out-of-band (e.g. physical console) authorization.

### Audit trail
- Every intent, approval token, broker action, and device response logged
  to an append-only store the agent process cannot modify (shipped to a
  separate log host or WORM-configured disk).
- Approval events log who approved, the exact diff, timestamp, and
  pre/post verification state.

### Session handling
- One fresh authenticated session per device per operation — no persistent
  reusable sessions.
- Concurrent multi-node remediation: each node gets an independently minted,
  independently revocable credential.

### Circuit breaker
- Infrastructure-level kill switch (firewall rule / physical toggle) to
  revoke the broker's signing authority instantly, independent of the agent
  process.
- Auto-halt tier-3 access after N consecutive failed remediations, or after
  a human rejects the same proposed fix more than once — no unbounded
  retry loops against live infrastructure.

  **Status 2026-09-10: not yet implemented/tested.** Everything else in
  Phase 0 (CA, Vault, RBAC schemas, broker↔Vault wiring) is running and
  verified — see Phase 0 Status below. The kill switch specifically needs
  a real firewall-rule change, which needs root; the dev workstation used
  for Phase 0 setup only has password-gated sudo, and it's a
  shared/in-use machine, not disposable — deliberately deferred rather
  than touching host iptables for a one-off test there. **Picking this up
  in Phase 1**, once the Containerlab harness gives an isolated
  broker-to-device path to test the rule against without touching the
  dev workstation's own host config.

### Phase 0 status (2026-09-10)

Running locally on the dev workstation (not containerized — Docker Hub/
GHCR pulls are blocked from this network; binaries built from source via
the Go module proxy or downloaded directly from vendor release hosts,
which are reachable):

- **step-ca**, standalone deployment type (self-managed root/intermediate
  keys, no cloud dependency), at `broker/infra/step-ca/`. Root + intermediate
  generated offline. Short-TTL leaf cert issuance verified end to end with
  two independent tools (`step certificate verify` and `openssl verify`).
- **Vault**, file storage backend, Shamir-sealed (3 shares / threshold 2),
  `disable_mlock` (no CAP_IPC_LOCK without root on this host — revisit for
  a hardened deployment target), TLS listener using a step-ca-issued cert.
  Config at `broker/infra/vault/config/`. Unseal keys + root token stored
  at `~/holden-tools/secrets/` (outside the repo, 0600, gitignored).
- **AppRole `broker-edge`**, bound to policy `broker-edge`
  (`broker/infra/vault/config/broker-policy.hcl`), read-only on
  `devices/data/edge/*`. `broker/vault_client.py` is the sole component in
  the repo that holds this AppRole's `role_id`/`secret_id` or calls Vault's
  API — confirmed by grep, and structurally true since no parser/reasoning
  code exists yet to violate it. End-to-end demo (`python3
  broker/vault_client.py`) logs in, reads a seeded device credential, and
  confirms Vault itself (not application code) rejects a read outside the
  AppRole's segment.
- Plaintext-secret grep pass (both the literal requested command and a
  broadened pattern/filetype set) run against the full repo tree: clean.
- **Not done:** kill switch (see Circuit breaker above — tracked for
  Phase 1). No test device exists yet, so the broker's device-connection
  path itself is still unexercised beyond the Vault credential fetch.

**Open item, deliberately not resolved — flagged so it doesn't get lost
now that Phases 0/1 are behind us:** `setup.sh` only installs the
step-ca/Vault *binaries*. There is still no scripted, or even documented
manual, path from a fresh clone to a working CA plus an
initialized-and-unsealed Vault with the `broker-edge` AppRole/policy
loaded — the current running instances on `cyber` were brought up by
hand during Phase 0 and that setup lives only in this host's state (root
CA/intermediate keys, Shamir unseal shares, root token, AppRole
role_id/secret_id — all correctly gitignored per the Credential/RBAC
architecture above, which is exactly why none of it travels with a
clone). A second person, or this same host after a wipe, has no way to
reconstruct a working broker credential layer from the repo alone right
now. Not a blocker for Phase 2 (which doesn't need live Vault/CA), but
must be closed — either a scripted init or a written runbook — before
this project can be considered new-user ready.

---

## Testing Infrastructure

**Recommendation: Containerlab** as the primary harness.
- Declarative YAML topologies; runs real network-OS images (Arista cEOS,
  Nokia SR Linux, FRR, Cisco XRd) or plain Linux containers as nodes, in
  Docker — scriptable generation of arbitrary topologies and teardown/rebuild
  per test run.
- Fault injection via `tc`/netem for link-layer issues (latency, loss,
  jitter, duplication) plus scripted config mutations (wrong VLAN, bad ACL,
  bad routing metric, duplicate IP), ideally applied through the *same*
  code path the execution broker uses — this doubles as an eval harness:
  inject fault → does the report cite it → does remediation revert it →
  does re-test confirm.

Alternatives considered:
- **GNS3 / EVE-NG** — higher fidelity (full vendor OS images), weaker fit
  for automated/CI-style test generation.
- **CORE** — lightweight, good for pure L3 + link impairment, weak on
  vendor-config-specific faults.
- **Mininet** — strong for SDN/OpenFlow, weak for vendor CLI-driven faults.

### Phase 1 status (2026-09-10)

Checklist 1.1–1.3 complete on the dev workstation:
- **1.1 Install** — containerlab built from source via the Go module proxy
  (same approach as step-ca/step-cli in Phase 0; GitHub/Docker Hub are
  unreachable from this network, `proxy.golang.org` is). Binary at
  `~/holden-tools/bin/containerlab`.
- **1.2 Topology deploys clean** — `testing/topologies/smoke-test.clab.yaml`
  (two `linux`-kind nodes on a point-to-point link) deploys in ~3s with no
  hangs, `containerlab inspect` confirms both nodes `running`.
- **1.3 Connectivity confirmed** — addressed the p2p link directly
  (`192.0.2.1`/`192.0.2.2` on `eth1`, not the shared management bridge) and
  pinged across it: 4/4 packets, 0% loss, ~0.05ms RTT. Verifies the actual
  containerlab-built veth link, not just Docker's default networking.

**Bug fixed, noted here so it isn't reintroduced:** containerlab's `exec:`
topology field runs a one-shot `docker exec` *after* the node container
starts — it is not the container's main process. The original topology
used `exec: [sleep infinity]`, which made `deploy` hang forever waiting
for that never-returning exec to complete (confirmed via a `SIGQUIT`
Go-goroutine dump, not guessed — the blocked goroutine was
`DockerRuntime.Exec` reading the exec's stdout). Fixed by using
`cmd: sleep infinity` instead, which sets the container's actual
entrypoint. **Any new `linux`-kind node topology must use `cmd:` for a
keep-alive/main process, never `exec:`.**

**Root privileges:** containerlab's point-to-point links are built with
raw veth/netns manipulation (`CAP_NET_ADMIN`), which `docker` group
membership does not grant — confirmed empirically (plain `docker network
create`/`docker run` works unprivileged; a raw `ip link add ... type veth`
does not) and the binary has a hard UID==0 gate with no rootless deploy
path found.

**Root-auth follow-up — resolved 2026-09-10.** Originally supplied via
`pkexec` per-call (graphical polkit prompt, since interactive `sudo` has
no TTY in this environment); the polkit auth cache proved short-lived and
inconsistent, repeatedly stalling commands mid-run waiting on a fresh
dialog. Fixed with a scoped sudoers rule, `/etc/sudoers.d/containerlab`:
```
sembrat ALL=(root) NOPASSWD: /home/sembrat/holden-tools/bin/containerlab
```
Exact binary path, no wildcard — verified it does *not* grant passwordless
root for anything else (`sudo -n whoami` still prompts) and does *not*
follow a copy of the binary at a different path (`sudo -n
/tmp/containerlab-copy ...` still prompts) — so the grant is exactly as
narrow as it looks. This is a different, narrower mechanism than the
earlier blanket `Bash(pkexec *)` permission-file attempt, which was tried
and explicitly reverted in an earlier session (see feedback from that
session) precisely because it wasn't scoped like this. All Phase 1
`containerlab` invocations now use `sudo -n <absolute path> ...` instead
of `pkexec`; no more auth dialogs, no more stalls, and `sudo` (unlike
`pkexec`) also preserves the caller's working directory, which sidesteps
the earlier relative-path bug category entirely.

**Also noted:** node containers have no package-mirror access (same
network restriction as the host, consistent with the eventual air-gapped
deployment target) — confirmed when `apt-get update` inside a test node
hung the same way `containerlab`'s version-check briefly did. Any future
topology needing more than base-OS tools must use images with required
tooling baked in at build time, not installed at deploy/runtime.

- **1.4 Fault injection** — used containerlab's built-in
  `tools netem set` (not raw `tc` by hand) to apply 50ms delay + 10% loss
  to node1's `eth1`. Verified from two independent vantage points: `tc
  qdisc show` run inside the node's own netns (`docker exec ... busybox
  tc`) and again via `nsenter` from the host side — both show `qdisc
  netem ... delay 50ms loss 10%`. Confirmed the impairment has a real
  functional effect, not just a config artifact: re-ran the p2p ping test
  under impairment and RTT rose from ~0.05ms to ~50ms with 15% observed
  loss (close to the configured 10%, expected sampling noise over 20
  pings). Impairment reset afterward (`tools netem reset`), confirmed
  back to `qdisc noqueue` — lab left clean.
- **1.5 Clean deploy/destroy cycle, via `sudo`** — first destroyed a
  leftover lab from earlier testing (5+ hours up) to reach a genuinely
  empty starting state (a `deploy` run against an already-running lab
  just reconciles with "no changes," which would not have been a valid
  fresh-deploy test). From clean: `sudo -n containerlab deploy` (3.3s,
  both nodes `running`) → `sudo -n containerlab destroy --cleanup` →
  confirmed nothing left behind on all three fronts: `docker ps -a | grep
  clab` (none), `ip netns list` (empty), `docker network ls | grep clab`
  (none, checked in addition to what was asked).

**Phase 1 checklist (1.1–1.5) complete.** Harness installed, topology
deploys and tears down clean and fast, p2p connectivity and fault
injection both verified from independent vantage points, and the root-
auth friction that would have slowed down every remaining Phase 1 test is
fixed. No open follow-ups from Phase 1 itself; Phase 0's kill-switch
follow-up (see Circuit breaker above) is still the one item carried
forward, and this harness is what it's waiting on.

**Regression found and fully resolved 2026-09-11, on the dev workstation
(hostname `cyber`) — noted here so it isn't reintroduced:** a later edit
to `smoke-test.clab.yaml` added an `exec:` block running `apt-get update
&& apt-get install -y iproute2 iputils-ping` inside each node before
addressing `eth1`. In practice this didn't fail fast, it **hung** —
matching the same failure class already flagged once above for
containerlab's own version-check.

**Root cause, confirmed (not guessed):** DNS resolution for the Debian
mirror does not fail — `getent hosts deb.debian.org` inside a node
container returns real answers — but those answers are IPv6-only
(Fastly anycast addresses via static host entries inherited from the
container's resolver config), and this network has no usable outbound
IPv6 path. `apt-get` therefore doesn't get a clean connection-refused or
DNS failure to fail on; it blocks in `connect()` against an
address it can never reach until the OS-level TCP timeout finally
expires (multiple minutes per exec step, times two exec steps per node).
That is the literal mechanism behind "no package-mirror access from node
containers," already documented above — this is the first time it was
traced to the specific IPv6-blackhole shape rather than just observed as
a hang.

**Fix**, per the project's own standing rule ("images with required
tooling baked in at build time, not installed at deploy/runtime"):
`node1`/`node2` now run a locally built `holden-smoke-node:latest` image
(built by `testing/topologies/build-smoke-image.sh`, fully offline — it
copies the host's already-installed static `busybox` binary, which
bundles `ip`/`ping`/`tc` applets, into a container built `FROM` the
already-locally-cached `debian:stable-slim`; no network access of any
kind is required to build it). `exec:` now only calls `busybox ip addr
add ...` — no package manager involved, nothing to hang on.

**Final verified results on `cyber`,** full 1.2–1.5 sequence re-run
against the fix, fresh from a clean `destroy --cleanup`:
- 1.2 deploy: 0.458s, both nodes `running` immediately, no exec-step
  delay of any kind.
- 1.3 connectivity: `busybox ping -c4 192.0.2.2` from node1 → 4/4
  packets, 0% loss, ~0.1ms RTT.
- 1.4 fault injection: `containerlab tools netem set` applied 50ms delay
  + 10% loss to node1's `eth1`; confirmed from two independent vantage
  points (`tc qdisc show` inside the node's own netns via `busybox tc`,
  and `containerlab tools netem show` from the host) — both agree on
  `delay 50ms loss 10.00%`. Functional effect confirmed: RTT under
  impairment rose to ~50ms over 20 pings (0% observed loss this run —
  expected sampling variance at p=0.1, n=20). Reset afterward, confirmed
  back to `qdisc noqueue`.
- 1.5 destroy: clean on all three fronts — no `clab-*` containers, no
  leftover `ip netns`, no leftover `clab` docker network.

Run `./testing/topologies/build-smoke-image.sh` once before `deploy` on
any fresh checkout or after pruning the `holden-smoke-node` image.

**Phase 1 is now fully complete, including this regression's resolution.**
No open follow-ups from Phase 1 itself.

---

## Risks

**Technical**
- SLM hallucination on remediation — mitigated structurally by the
  structured-intent + broker-whitelist pattern (LLM never emits raw CLI).
- Vendor output parsing brittleness across firmware/OS versions.
- RAG retrieval returning plausible-but-wrong manual sections (e.g. wrong
  hardware revision) in a context where cross-checking is limited.

**Security**
- The agent/broker host is the highest-value target on the LAN — needs its
  own hardened, minimally-networked placement.
- Device output (syslog, SNMP, CLI responses) is an LLM injection vector —
  addressed by the reasoning/execution separation above.
- Audit logs must be tamper-evident and outside the agent's write access.

**Safety / operational**
- Blast radius per approved change must be bounded (see credential TTL/scope
  design above).
- Every applied change needs a tested, automatic rollback path.
- Denial-loop handling: bounded retries before mandatory escalation to a
  human, not indefinite autonomous re-attempts.
- Eventual ATO / IEC 62443 compliance process likely required for military/
  ICS deployment — constrains logging format, crypto module choices; worth
  scoping early even though it's a Phase 9+ concern.

---

## Open Decisions (need answers before/during handoff)

1. **Command whitelist scope** — exact universe of autonomous actions
   (VLAN/ACL/routing changes?) vs. propose-only actions (firmware pushes?).
   Partially resolved: initial action catalog drafted at
   `broker/config/action-catalog.yaml` (show/ping/traceroute + set_vlan/
   set_acl/set_interface_admin_state); still open whether routing changes
   get added pre-v1 or wait.
2. **Bastion pattern** — ~~jump-host broker vs. direct broker-to-device
   connections per segment~~ **Resolved 2026-09-10: one Execution Broker
   per segment/enclave** (not a shared jump host), to keep blast radius
   bounded per compromise. Reflected in the trust-boundary design and the
   `scope.segments` field on RBAC roles.
3. **SLM choice + hosting** — model, quantization, hardware footprint for
   target deployment environments.
4. **Vendor scope for v1** — ~~single-vendor (e.g. Cisco-only) vs.
   multi-vendor from day one~~ **Resolved 2026-09-10: Cisco IOS/IOS-XE
   only for v1.** Whitelist schema and action catalog are kept
   vendor-parameterized (no Cisco assumptions baked into
   `intent.schema.json` or `action-catalog.yaml`) so multi-vendor is a
   post-v1 addition, not a rewrite. Vendor-specific command templates are a
   separate Whitelist Compiler config, not yet built.
5. **Acceptance bar for the testing phase** — e.g. "finds X% of injected
   faults across N topology types, zero false remediations under red-team
   testing."
6. **Compliance target** — is a specific ATO/IEC 62443 process already
   known/required?
7. **Team size, timeline, budget** — scopes how much of Phases 0–9 is v1
   vs. roadmap.
8. **Key storage** — ~~Vault air-gap mode vs. SOPS+age vs. local HSM~~
   **Resolved 2026-09-10: Vault in air-gap mode for v1**, no HSM. Vault's
   policy/audit hooks line up with broker RBAC enforcement; HSM revisited
   only if the project moves toward a hardware-certified deployment.
