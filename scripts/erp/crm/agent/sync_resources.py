"""Check or refresh the canonical CRM agent resource projections."""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PROJECTIONS = {
    ".agents/domains/crm/agent_card.json": ".agents/agent_card.json",
    ".tau/domains/crm/SYSTEM.md": ".tau/SYSTEM.md",
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    for source, destination in PROJECTIONS.items():
        expected = (ROOT / source).read_bytes()
        if args.write:
            (ROOT / destination).write_bytes(expected)
        elif (ROOT / destination).read_bytes() != expected:
            parser.exit(1, f"Stale CRM projection: {destination}; run with --write.\n")
    print("CRM agent resource projections are synchronized.")

if __name__ == "__main__":
    main()
