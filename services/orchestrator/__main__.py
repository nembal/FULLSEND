"""Run orchestrator daemon: python -m services.orchestrator"""

import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Run from repo root: python -m services.orchestrator
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    from .runner import run_orchestrator_daemon

    run_orchestrator_daemon()
