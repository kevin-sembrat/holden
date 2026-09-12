"""
Reasoning core: structured diagnosis output (Phase 4, checklist 4.2).

Takes a parsed show_interface result (parser/schemas/show_interface_result.schema.json)
and asks the local model (llama3.2:1b via Ollama, see Phase 4.1) to produce a
diagnosis. The model is responsible only for the semantic content --
finding/confidence/evidence/explanation/recommended_action -- everything
structural (diagnosis_id/timestamp/correlation_id/target) is filled in by
this harness, never requested from the model. See
reasoning/schemas/diagnosis_result.schema.json's description for why.

The merged result is validated four ways, because a 1B model's failure
modes span all four and jsonschema alone catches only one of them:
  1. Is it well-formed JSON with no duplicate keys? (plain json.loads
     accepts duplicate keys and silently keeps the last value -- observed
     in testing: a response with two "explanation" keys, where the
     model's second, nonsensical value for the second occurrence
     silently overwrote the real one with no error at all. See
     _reject_duplicate_keys.)
  2. Does it match the schema shape? (jsonschema.validate -- catches wrong
     key names, extra keys, wrong types)
  3. Is the content actually grounded in the real input, or did the model
     just parrot the in-prompt format example / hallucinate unrelated
     content? (jsonschema can't express this -- see check_content_grounded
     below. A first prompt draft that included one worked example got
     schema-valid JSON back that was a verbatim copy of the example,
     completely ignoring the real input -- passing (1) and (2) while
     being useless.)
  4. Is recommended_action, if not null, an action that actually exists
     in the catalog? (schema-shape-valid strings like "set_counters" are
     not automatically catalog-valid.)

Since (1)-(4) aren't reliably satisfied on the first attempt from a 1B
model, this runs a bounded retry loop and reports how many attempts it
actually took -- not a formality, an honest measurement.
"""

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib import request as urllib_request

import jsonschema
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSIS_SCHEMA_PATH = REPO_ROOT / "reasoning" / "schemas" / "diagnosis_result.schema.json"
ACTION_CATALOG_PATH = REPO_ROOT / "broker" / "config" / "action-catalog.yaml"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "llama3.2:1b"
MAX_ATTEMPTS = 5


def load_allowed_actions() -> set:
    with open(ACTION_CATALOG_PATH) as f:
        catalog = yaml.safe_load(f)
    return set(catalog.get("actions", {}).keys())


def build_prompt(show_interface_result: dict, allowed_actions: list) -> str:
    """No worked example with realistic content: an earlier version included one and the
    model copied its finding/evidence/recommended_action verbatim, ignoring the real input
    entirely, while still passing schema validation. Shape is instead specified as a plain
    key list with explicit constraints, which fixed the copying problem (see module docstring
    and the Phase 4.2 report for the actual before/after)."""
    return f"""You are a network diagnostics assistant analyzing a network device fault.

Input show_interface result (this is the actual data you must diagnose -- base your answer only on these values):
{json.dumps(show_interface_result, indent=2)}

Pay particular attention to the counters field (input_errors, crc_errors, frame_errors, runts, giants) relative to each other, and to admin_state/oper_state.

Respond with a JSON object containing EXACTLY these five keys, spelled exactly this way, and no other keys of any kind:
finding, confidence, evidence, explanation, recommended_action

Key requirements:
- finding: a SHORT label, 2 to 4 words, lowercase_snake_case, not a full sentence
- confidence: exactly one of the strings "low", "medium", or "high"
- evidence: a JSON array of strings; each string must name a specific field and its actual value from the input above, e.g. "crc_errors is 14980"
- explanation: one or two sentences of reasoning
- recommended_action: the JSON value null, OR exactly one of these strings with no other words added: {json.dumps(allowed_actions)}

Do not include admin_state, oper_state, or any field name from the input as a top-level key in your answer -- those five keys only.
Output ONLY the JSON object itself. No markdown code fences, no text before or after it.
"""


def call_model(prompt: str) -> str:
    body = json.dumps({"model": MODEL, "prompt": prompt, "stream": False}).encode()
    req = urllib_request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib_request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())["response"]


def strip_markdown_fence(text: str) -> str:
    """Some small models wrap JSON in ```json ... ``` despite instructions not to. Strip it if present."""
    text = text.strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return match.group(1) if match else text


def _reject_duplicate_keys(pairs: list) -> dict:
    """Plain json.loads silently keeps the *last* value for a repeated key -- legal JSON,
    but a strong sign the model's generation went off the rails mid-object (observed: a
    model output with 'explanation' and 'recommended_action' each appearing twice, where
    the second, nonsensical occurrence silently overwrote the real one -- json.loads alone
    accepted it as valid with no error, corrupting the result invisibly). Raise instead of
    silently picking one."""
    seen = set()
    result = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key {key!r} in model output -- refusing to silently pick one value over the other")
        seen.add(key)
        result[key] = value
    return result


def parse_strict_json(text: str) -> dict:
    return json.loads(text, object_pairs_hook=_reject_duplicate_keys)


def check_content_grounded(diagnosis: dict, show_interface_result: dict) -> None:
    """jsonschema can only check shape, not whether the model actually looked at the real
    input. Requires at least one evidence string to reference an actual counter field name
    or value from the input -- catches both verbatim-copied-the-example and generic/
    hallucinated-unrelated-content failures."""
    counters = show_interface_result.get("counters", {})
    real_tokens = [str(k) for k in counters.keys()] + [str(v) for v in counters.values()]
    evidence_text = " ".join(diagnosis.get("evidence", [])).lower()

    if not any(token.lower() in evidence_text for token in real_tokens):
        raise ValueError(
            f"evidence {diagnosis.get('evidence')!r} doesn't reference any real counter "
            f"field/value from the input ({real_tokens}) -- looks unrelated to the actual data"
        )


def validate_diagnosis(diagnosis: dict, allowed_actions: set, show_interface_result: dict) -> None:
    schema = json.loads(DIAGNOSIS_SCHEMA_PATH.read_text())
    jsonschema.validate(diagnosis, schema)

    recommended = diagnosis.get("recommended_action")
    if recommended is not None and recommended not in allowed_actions:
        raise ValueError(
            f"recommended_action {recommended!r} is schema-shape-valid (a string) "
            f"but is not an action in the real catalog {sorted(allowed_actions)}"
        )

    check_content_grounded(diagnosis, show_interface_result)


def attempt_diagnosis(prompt: str, show_interface_result: dict, target: dict, correlation_id: str, allowed_actions: set):
    """One attempt. Returns (diagnosis_or_None, raw_output, error_or_None)."""
    raw_output = call_model(prompt)
    cleaned = strip_markdown_fence(raw_output)

    try:
        model_fields = parse_strict_json(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        return None, raw_output, f"not valid JSON: {e}"

    diagnosis = {
        "diagnosis_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "correlation_id": correlation_id,
        "target": target,
        "based_on": {"action": "show_interface", "interface": show_interface_result["interface"]},
        **(model_fields if isinstance(model_fields, dict) else {}),
    }

    try:
        validate_diagnosis(diagnosis, allowed_actions, show_interface_result)
    except (jsonschema.ValidationError, ValueError) as e:
        return None, raw_output, str(e)

    return diagnosis, raw_output, None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("show_interface_file", type=Path)
    ap.add_argument("--segment", default="lab")
    ap.add_argument("--device-class", default="switch")
    ap.add_argument("--device-id", default="test-switch-01")
    ap.add_argument("--correlation-id", default=None)
    ap.add_argument("--max-attempts", type=int, default=MAX_ATTEMPTS)
    args = ap.parse_args()

    correlation_id = args.correlation_id or f"diag-session-{uuid.uuid4()}"
    show_interface_result = json.loads(args.show_interface_file.read_text())
    target = {"segment": args.segment, "device_class": args.device_class, "device_id": args.device_id}
    allowed_actions = load_allowed_actions()

    prompt = build_prompt(show_interface_result, sorted(allowed_actions))
    print("=== PROMPT SENT ===")
    print(prompt)

    for attempt in range(1, args.max_attempts + 1):
        diagnosis, raw_output, error = attempt_diagnosis(prompt, show_interface_result, target, correlation_id, allowed_actions)
        print(f"\n=== ATTEMPT {attempt} RAW MODEL OUTPUT ===")
        print(raw_output)

        if diagnosis is not None:
            print(f"\n=== ATTEMPT {attempt}: PASSED (JSON valid, schema valid, content grounded) ===")
            print(json.dumps(diagnosis, indent=2))
            print(f"\n=== SUCCEEDED on attempt {attempt}/{args.max_attempts} ===")
            return 0

        print(f"=== ATTEMPT {attempt}: FAILED: {error} ===")

    print(f"\n=== FAILED after {args.max_attempts} attempts, no valid+grounded diagnosis produced ===", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
