"""
Parser for the show_interface action (Phase 2, checklist 2.2).

Converts raw 'ip addr show <interface>' text -- what show_interface maps to
on the Phase 1 test lab's generic Linux nodes, in the absence of a real
Cisco IOS-XE test device (see project-holden-scope.md, Phase 0 status) --
into the structured shape defined by parser/schemas/show_interface_result.schema.json.

Pure stdlib regex/line parsing, no new dependency, mirroring the
stdlib-only precedent set by broker/vault_client.py.
"""

import argparse
import json
import re
import sys
from pathlib import Path

_HEADER_RE = re.compile(r"^\d+:\s+(?P<iface>\S+?)(@\S+)?:\s+<(?P<flags>[^>]*)>\s+mtu\s+(?P<mtu>\d+)")
_MAC_RE = re.compile(r"^\s*link/\S+\s+(?P<mac>[0-9a-fA-F:]+)")
_INET_RE = re.compile(r"^\s*inet\s+(?P<addr>[\d.]+)/(?P<plen>\d+)")
_INET6_RE = re.compile(r"^\s*inet6\s+(?P<addr>[0-9a-fA-F:]+)/(?P<plen>\d+)\s+scope\s+(?P<scope>\S+)")


class ParseError(Exception):
    """Raw text didn't match the expected 'ip addr show' shape -- a clean error, not a crash or a guess."""


def parse_show_interface(raw_text: str) -> dict:
    lines = raw_text.splitlines()

    header_match = None
    for line in lines:
        header_match = _HEADER_RE.match(line)
        if header_match:
            break
    if header_match is None:
        raise ParseError("no interface header line found (expected '<N>: <iface>: <...flags...> mtu <N> ...')")

    flags = set(header_match.group("flags").split(","))
    result = {
        "interface": header_match.group("iface"),
        "admin_state": "up" if "UP" in flags else "down",
        "oper_state": "up" if "LOWER_UP" in flags else "down",
        "mtu": int(header_match.group("mtu")),
        "mac_address": None,
        "ipv4_addresses": [],
        "ipv6_addresses": [],
    }

    for line in lines:
        m = _MAC_RE.match(line)
        if m:
            result["mac_address"] = m.group("mac")
            continue
        m = _INET_RE.match(line)
        if m:
            result["ipv4_addresses"].append({"address": m.group("addr"), "prefix_length": int(m.group("plen"))})
            continue
        m = _INET6_RE.match(line)
        if m:
            result["ipv6_addresses"].append(
                {"address": m.group("addr"), "prefix_length": int(m.group("plen")), "scope": m.group("scope")}
            )
            continue

    if result["mac_address"] is None:
        raise ParseError("no 'link/...' line found -- could not determine mac_address")

    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Parse raw 'ip addr show <iface>' output into structured JSON.")
    ap.add_argument("raw_output_file", type=Path, help="Path to a text file containing raw command output")
    args = ap.parse_args()

    try:
        raw_text = args.raw_output_file.read_text()
    except OSError as e:
        print(json.dumps({"error": f"could not read raw output file: {e}"}, indent=2))
        return 2

    try:
        result = parse_show_interface(raw_text)
    except ParseError as e:
        print(json.dumps({"error": str(e)}, indent=2))
        return 2

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
