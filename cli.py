"""SolScribe CLI. Examples:
  python cli.py --demo
  python cli.py <TX_SIGNATURE> --network devnet --level developer
  python cli.py <WALLET_ADDRESS> --network devnet
"""
import argparse
import sys

import core


def main() -> int:
    p = argparse.ArgumentParser(description="Explain Solana transactions in plain English.")
    p.add_argument("target", nargs="?", help="transaction signature or wallet address")
    p.add_argument("--network", choices=list(core.NETWORKS), default="devnet")
    p.add_argument("--level", choices=["beginner", "developer"], default="beginner")
    p.add_argument("--no-ai", action="store_true", help="skip the Claude explanation")
    p.add_argument("--demo", action="store_true", help="use the built-in sample transaction (offline)")
    a = p.parse_args()

    try:
        if a.demo:
            summary = core.summarize(core.load_sample())
        else:
            if not a.target:
                p.error("give a signature/address or use --demo")
            kind = core.detect_input_type(a.target)
            if kind == "invalid":
                print("That doesn't look like a Solana signature or address.")
                return 1
            if kind == "address":
                print(f"Balance: {core.fetch_balance_sol(a.target, a.network):.4f} SOL ({a.network})")
                sigs = core.fetch_recent_signatures(a.target, 5, a.network)
                print("Recent transactions:")
                for s in sigs:
                    print(f"  {'OK ' if not s.get('err') else 'ERR'} {s['signature']}")
                print("\nRe-run with one of these signatures to get an explanation.")
                return 0
            summary = core.summarize(core.fetch_transaction(a.target, a.network))
        text, source = core.explain(summary, a.level, use_ai=not a.no_ai)
        print(f"[explanation source: {source}]\n")
        print(text)
        return 0
    except core.SolScribeError as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
