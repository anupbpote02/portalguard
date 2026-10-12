"""PortalGuard entry point.

    python -m agent.main --mock                          # scripted fake LLM, $0, no API key
    python -m agent.main --mock --scenario guardrails    # misbehaving model: bad args, off-site URLs
    python -m agent.main --mock --scenario runaway       # looping model: stopped by MAX_STEPS
    python -m agent.main                                 # live: gpt-4.1-mini, key from .env

The portal must be running:  python -m http.server 8000 --directory portal
"""

import argparse
import sys
import urllib.request
from urllib.error import URLError

from dotenv import load_dotenv

from agent.harness import PRICES_PER_1M, Harness
from agent.llm import MOCK_SCENARIOS, MockLLM, OpenAILLM

EXIT_CODES = {"done": 0, "llm_error": 1}  # any budget / policy stop -> 3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline", default="http://localhost:8000/good/", help="last good release")
    parser.add_argument("--release", default="http://localhost:8000/buggy/", help="release under test")
    parser.add_argument("--mock", action="store_true", help="use the scripted fake LLM ($0, no key)")
    parser.add_argument("--scenario", choices=sorted(MOCK_SCENARIOS), default="qe", help="mock script to replay")
    args = parser.parse_args()

    try:
        urllib.request.urlopen(args.baseline, timeout=3)
    except (URLError, ValueError):
        print(f"Portal not reachable at {args.baseline}\nStart it first:  python -m http.server 8000 --directory portal")
        return 2

    if args.mock:
        llm = MockLLM(MOCK_SCENARIOS[args.scenario](args.baseline, args.release))
    else:
        load_dotenv()  # the API key only ever comes from .env / the environment
        try:
            llm = OpenAILLM()
        except RuntimeError as e:
            print(e)
            return 1

    summary = Harness(llm, args.baseline, args.release).run()

    print(f"\nPortalGuard run ({llm.model}{', scenario ' + args.scenario if args.mock else ''})")
    print(f"  stop reason : {summary['stop_reason']}")
    print(f"  steps       : {summary['steps']} LLM calls, {summary['tool_calls']} tool calls "
          f"({summary['blocked_calls']} blocked)")
    print(f"  tokens      : {summary['total_tokens']:,}")
    print(f"  cost        : ${summary['total_cost_usd']:.4f}", end="")
    if args.mock:
        input_price, _ = PRICES_PER_1M["gpt-4.1-mini"]  # rough: mock tokens are mostly prompt
        print(f"  (same tokens on gpt-4.1-mini: ~${summary['total_tokens'] * input_price / 1e6:.4f})", end="")
    print(f"\n  duration    : {summary['duration_s']}s")
    print(f"  trace       : {summary['trace']}")
    if summary["final_message"]:
        print(f"  final       : {summary['final_message']}")
    return EXIT_CODES.get(summary["stop_reason"], 3)


if __name__ == "__main__":
    sys.exit(main())
