"""
Shared logging setup for the Parser/Tool layer (Phase 2, checklist 2.4).

Both parser/whitelist_check.py and parser/show_interface_parser.py were
silent before this -- stdout-only JSON results, nothing durable to audit.
This gives them a real, persistent log (parser/logs/parser.log, appended
across runs) so "confirm no credential leakage in parser logs" is checking
actual content, not an empty file. Logged verbosely and on purpose --
full intents, full parsed results -- specifically so this becomes a
meaningful test of the credential architecture (intents and device
telemetry are never supposed to carry credential material -- see
broker/schemas/intent.schema.json and the Credential/RBAC Architecture
section of project-holden-scope.md), not just a happy-path smoke check.
"""

import logging
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "parser" / "logs"
LOG_FILE = LOG_DIR / "parser.log"


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured (e.g. re-imported in a test run)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
