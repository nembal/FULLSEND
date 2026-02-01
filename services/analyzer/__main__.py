"""Run analyzer agent: python -m services.analyzer"""

import logging
import sys

from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    from .runner import run_analyzer

    result = run_analyzer()
    print("\n--- Builder tasks (published to builder queue) ---\n")
    print(result["summary"])
