# solscribe-solana-explainer
Explains Solana transactions in plain English, for beginners and developers. Python + Streamlit.

# 📜 SolScribe: Solana, explained in plain English

Paste any Solana transaction signature and SolScribe tells you what happened: who paid, where the SOL and tokens went,
which programs ran, and why it matters. It has a **beginner mode** and a **developer mode**, a built-in "Learn Solana"
glossary, and a wallet overview. It is read-only: no wallet, keys or Rust needed.

**Why:** a Solana transaction is raw JSON with account indexes and lamports. Newcomers can't read it. SolScribe is an
on-ramp: it parses the chain data deterministically, then uses AI (Claude) only to *narrate* verified facts. If no API
key is set, a rule-based explainer takes over, so the tool never breaks.

## Run it
```bash
pip install -r requirements.txt
streamlit run app.py                 # web app
python cli.py --demo                 # offline demo, no network
python cli.py <TX_SIGNATURE> --network devnet --level developer
python cli.py <WALLET_ADDRESS> --network devnet
python -m pytest -q                  # tests
```
Optional AI mode: `export ANTHROPIC_API_KEY=...` (or paste it in the app sidebar). Optional: `SOLSCRIBE_MODEL` to change the model.

## How it works
1. `core.fetch_transaction` calls Solana JSON-RPC `getTransaction` (jsonParsed encoding).
2. `core.summarize` computes SOL/token balance deltas from pre/post balances, decodes known instructions
   (System, SPL Token, Associated Token, Memo), and labels known programs.
3. `core.explain` sends only that verified summary to Claude with a "use only these facts" prompt, falling back to rules.

## Limits (honest)
- Read-only: it does not write to the chain or deploy a program.
- Recognises a small built-in set of programs; others show as "Unknown program".
- Public RPC endpoints are rate-limited. Use your own RPC URL via `core.rpc_call(rpc_url=...)` for heavy use.

## Ideas for next steps
Swap/NFT-specific decoders, a "scam-risk hints" panel, Solana Pay QR explainer, an on-chain memo "receipt" written to devnet.
