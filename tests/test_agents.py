"""Smoke test for src/agents.ask. Run directly: python tests/test_agents.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from src.agents import ask

if __name__ == "__main__":
    response = ask("say hello")
    print(response)
