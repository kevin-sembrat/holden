"""
Whitelist-enforcement gate for the Parser/Tool layer (Phase 2, checklist 2.1).

Validates a structured intent (see broker/schemas/intent.schema.json) against
broker/config/action-catalog.yaml and broker/config/global-deny-list.yaml
*before* any device contact is attempted. Mirrors the fail-closed posture
described throughout project-holden-scope.md: an action absent from the
catalog, or present on the deny list, is rejected -- never silently ignored,
never let through by falling into a permissive default.

Scope, deliberately narrow: this is the first, cheapest gate an intent must
clear -- does the broker's action catalog even recognize this action, and is
it categorically denied. It does not connect to a device, mint credentials,
resolve vendor, or evaluate per-role RBAC scope (segment/device_class/
max_tier) -- those are later Phase 2.x / Phase 6 concerns, layered on top of
this gate rather than folded into it.
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from logging_setup import get_logger

REPO_ROOT = Path(__file__).resolve().parent.parent
ACTION_CATALOG_PATH = REPO_ROOT / "broker" / "config" / "action-catalog.yaml"
GLOBAL_DENY_LIST_PATH = REPO_ROOT / "broker" / "config" / "global-deny-list.yaml"

log = get_logger("holden.parser.whitelist_check")


class WhitelistError(Exception):
    """A malformed intent -- distinct from a *rejected* intent, which is a normal, expected outcome."""


@dataclass
class WhitelistResult:
    accepted: bool
    action: str
    reasons: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"accepted": self.accepted, "action": self.action, "reasons": self.reasons}


def _load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_action_catalog(path: Path = ACTION_CATALOG_PATH) -> dict:
    return _load_yaml(path).get("actions", {})


def load_global_deny_list(path: Path = GLOBAL_DENY_LIST_PATH) -> set:
    return set(_load_yaml(path).get("denied_actions", []))


def check_intent(intent: dict, catalog: dict = None, deny_list: set = None) -> WhitelistResult:
    """The whitelist-enforcement gate itself. Fail-closed: anything short of an
    exact catalog match with no deny-list hit is a rejection, not a warning."""
    catalog = load_action_catalog() if catalog is None else catalog
    deny_list = load_global_deny_list() if deny_list is None else deny_list

    log.info("checking intent: %s", json.dumps(intent))

    if not isinstance(intent, dict) or "action" not in intent:
        log.error("rejected: malformed intent, missing required 'action' field")
        raise WhitelistError("malformed intent: missing required 'action' field")

    action = intent["action"]
    reasons = []

    if action in deny_list:
        reasons.append(
            f"'{action}' is on the global deny list (broker/config/global-deny-list.yaml) -- "
            "hard-denied regardless of role, excluded from the autonomous loop entirely in v1"
        )

    if action not in catalog:
        reasons.append(
            f"'{action}' is not defined in the action catalog (broker/config/action-catalog.yaml) -- "
            "unrecognized actions are rejected before reaching policy evaluation"
        )

    if reasons:
        log.warning("rejected action=%r: %s", action, "; ".join(reasons))
        return WhitelistResult(accepted=False, action=action, reasons=reasons)

    result = WhitelistResult(
        accepted=True,
        action=action,
        reasons=[f"'{action}' found in action catalog (tier {catalog[action]['tier']}), not on the deny list"],
    )
    log.info("accepted action=%r tier=%s", action, catalog[action]["tier"])
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate a structured intent against the action catalog and global deny list.")
    ap.add_argument("intent_file", type=Path, help="Path to a JSON file containing one intent object")
    args = ap.parse_args()

    log.info("reading intent file: %s", args.intent_file)
    try:
        intent = json.loads(args.intent_file.read_text())
    except (OSError, json.JSONDecodeError) as e:
        log.error("could not read/parse intent file %s: %s", args.intent_file, e)
        print(json.dumps({"accepted": False, "error": f"could not read/parse intent file: {e}"}, indent=2))
        return 2

    try:
        result = check_intent(intent)
    except WhitelistError as e:
        print(json.dumps({"accepted": False, "error": str(e)}, indent=2))
        return 2

    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.accepted else 1


if __name__ == "__main__":
    sys.exit(main())
