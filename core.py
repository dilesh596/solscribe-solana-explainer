"""SolScribe core: fetch Solana data, parse it, and explain it in plain English."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

NETWORKS = {
    "devnet": "https://api.devnet.solana.com",
    "testnet": "https://api.testnet.solana.com",
    "mainnet": "https://api.mainnet-beta.solana.com",
}
LAMPORTS_PER_SOL = 1_000_000_000
BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]+$")
SAMPLE_PATH = Path(__file__).parent / "sample_tx.json"

# program id -> (name, one-line beginner explanation)
KNOWN_PROGRAMS = {
    "11111111111111111111111111111111": ("System Program", "Core Solana program: creates accounts and moves SOL."),
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": ("SPL Token Program", "Standard program for fungible tokens (like USDC)."),
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb": ("Token-2022 Program", "Newer token program with extra features."),
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": ("Associated Token Account Program", "Creates the token account a wallet needs to hold a token."),
    "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr": ("Memo Program", "Lets you attach a short text note to a transaction."),
    "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo": ("Memo Program (v1)", "Lets you attach a short text note to a transaction."),
    "ComputeBudget111111111111111111111111111111": ("Compute Budget Program", "Sets compute limits and priority fees."),
    "Stake11111111111111111111111111111111111111": ("Stake Program", "Handles staking SOL with validators."),
    "Vote111111111111111111111111111111111111111": ("Vote Program", "Used by validators to vote on blocks."),
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": ("Jupiter v6", "A swap router that finds the best price across exchanges."),
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": ("Raydium AMM", "A decentralized exchange (token swaps and liquidity pools)."),
    "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s": ("Metaplex Token Metadata", "Stores names and images for NFTs and tokens."),
    "BPFLoaderUpgradeab1e11111111111111111111111": ("Upgradeable BPF Loader", "Deploys and upgrades Solana programs."),
}


class SolScribeError(Exception):
    """A user-facing error."""


# ---------- helpers ----------
def short(addr: str | None, n: int = 4) -> str:
    if not addr:
        return "?"
    return addr if len(addr) <= 2 * n + 1 else f"{addr[:n]}…{addr[-n:]}"


def detect_input_type(text: str) -> str:
    """Return 'signature', 'address' or 'invalid'."""
    t = (text or "").strip()
    if not t or not BASE58_RE.match(t):
        return "invalid"
    if 80 <= len(t) <= 90:
        return "signature"
    if 32 <= len(t) <= 44:
        return "address"
    return "invalid"


def program_name(pid: str) -> str:
    return KNOWN_PROGRAMS.get(pid, (f"Unknown program ({short(pid)})", ""))[0]


def load_sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text())


# ---------- RPC ----------
def rpc_call(method: str, params: list, network: str = "devnet", rpc_url: str | None = None, timeout: int = 20):
    url = rpc_url or NETWORKS[network]
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise SolScribeError(
            f"Could not reach the Solana RPC ({e}). Public endpoints are rate-limited; wait a few seconds and retry."
        ) from e
    except ValueError as e:
        raise SolScribeError("The RPC returned something that is not JSON.") from e
    if "error" in data:
        err = data["error"]
        raise SolScribeError(f"RPC error: {err.get('message', err) if isinstance(err, dict) else err}")
    return data.get("result")


def fetch_transaction(signature: str, network: str = "devnet", rpc_url: str | None = None) -> dict:
    result = rpc_call(
        "getTransaction",
        [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}],
        network, rpc_url,
    )
    if result is None:
        raise SolScribeError(f"Transaction not found on {network}. Check the signature and the selected network.")
    return result


def fetch_balance_sol(address: str, network: str = "devnet", rpc_url: str | None = None) -> float:
    res = rpc_call("getBalance", [address], network, rpc_url)
    return res["value"] / LAMPORTS_PER_SOL


def fetch_recent_signatures(address: str, limit: int = 10, network: str = "devnet", rpc_url: str | None = None) -> list[dict]:
    return rpc_call("getSignaturesForAddress", [address, {"limit": limit}], network, rpc_url) or []


# ---------- parsing ----------
def _token_amount(info: dict) -> str:
    ta = info.get("tokenAmount")
    if isinstance(ta, dict):
        return ta.get("uiAmountString") or ta.get("amount", "?")
    return str(info.get("amount", "?"))


def describe_instruction(ix: dict) -> dict:
    pid = ix.get("programId", "")
    pname = program_name(pid)
    parsed = ix.get("parsed")
    out = {"program": pname, "program_id": pid, "type": "unparsed", "description": ""}

    if isinstance(parsed, str):  # memo programs return the text itself
        out.update(type="memo", description=f'Attached a note: "{parsed}"')
        return out

    if isinstance(parsed, dict):
        t = parsed.get("type", "unknown")
        info = parsed.get("info") or {}
        out["type"] = t
        if pid == "11111111111111111111111111111111":
            if t == "transfer":
                sol = info.get("lamports", 0) / LAMPORTS_PER_SOL
                out["description"] = f"Sent {sol:g} SOL from {short(info.get('source'))} to {short(info.get('destination'))}."
            elif t == "createAccount":
                sol = info.get("lamports", 0) / LAMPORTS_PER_SOL
                out["description"] = f"Created a new account {short(info.get('newAccount'))} funded with {sol:g} SOL."
        elif "Token Program" in pname or pname.startswith("Token-2022"):
            amt = _token_amount(info)
            if t in ("transfer", "transferChecked"):
                out["description"] = f"Moved {amt} tokens from token account {short(info.get('source'))} to {short(info.get('destination'))}."
            elif t in ("mintTo", "mintToChecked"):
                out["description"] = f"Minted {amt} new tokens to {short(info.get('account'))}."
            elif t in ("burn", "burnChecked"):
                out["description"] = f"Burned {amt} tokens from {short(info.get('account'))}."
            elif t == "closeAccount":
                out["description"] = f"Closed token account {short(info.get('account'))} and reclaimed its rent."
            elif t in ("approve", "approveChecked"):
                out["description"] = f"Approved {short(info.get('delegate'))} to spend {amt} tokens."
        elif "Associated Token" in pname:
            out["description"] = (f"Created a token account for wallet {short(info.get('wallet'))} "
                                  f"to hold mint {short(info.get('mint'))}.")
        if not out["description"]:
            out["description"] = f"{pname}: {t}."
        return out

    # unparsed instruction: describe by program
    blurb = KNOWN_PROGRAMS.get(pid, ("", ""))[1]
    out["description"] = f"Called {pname}." + (f" {blurb}" if blurb else "")
    return out


def summarize(tx: dict) -> dict:
    """Turn a raw jsonParsed getTransaction result into a clean summary dict."""
    meta = tx.get("meta") or {}
    msg = (tx.get("transaction") or {}).get("message") or {}
    keys = [k if isinstance(k, dict) else {"pubkey": k, "signer": False, "writable": False}
            for k in msg.get("accountKeys", [])]
    pubkeys = [k["pubkey"] for k in keys]
    signers = [k["pubkey"] for k in keys if k.get("signer")]
    fee_payer = pubkeys[0] if pubkeys else None

    sol_changes = []
    pre, post = meta.get("preBalances", []), meta.get("postBalances", [])
    for i, (a, b) in enumerate(zip(pre, post)):
        if b != a and i < len(pubkeys):
            sol_changes.append({"account": pubkeys[i], "change_sol": (b - a) / LAMPORTS_PER_SOL})

    def _tok(balances):
        d = {}
        for t in balances or []:
            ui = t.get("uiTokenAmount", {})
            d[t["accountIndex"]] = (t.get("owner"), t.get("mint"), int(ui.get("amount", 0)), ui.get("decimals", 0))
        return d

    pre_t, post_t = _tok(meta.get("preTokenBalances")), _tok(meta.get("postTokenBalances"))
    token_changes = []
    for idx in set(pre_t) | set(post_t):
        owner, mint, amt_b, dec = post_t.get(idx, (None, None, 0, 0))
        if idx in pre_t:
            owner_p, mint_p, amt_a, dec_p = pre_t[idx]
            owner, mint, dec = owner or owner_p, mint or mint_p, dec or dec_p
        else:
            amt_a = 0
        if amt_b != amt_a:
            token_changes.append({"owner": owner, "mint": mint, "change": (amt_b - amt_a) / (10 ** dec)})

    instructions = [describe_instruction(ix) for ix in msg.get("instructions", [])]
    programs, seen = [], set()
    for ix in msg.get("instructions", []):
        pid = ix.get("programId", "")
        if pid not in seen:
            seen.add(pid)
            programs.append({"id": pid, "name": program_name(pid), "about": KNOWN_PROGRAMS.get(pid, ("", ""))[1]})

    bt = tx.get("blockTime")
    when = datetime.fromtimestamp(bt, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if bt else "unknown"
    err = meta.get("err")
    sigs = (tx.get("transaction") or {}).get("signatures") or [""]
    return {
        "signature": sigs[0],
        "status": "success" if err is None else "failed",
        "error": err,
        "time": when,
        "slot": tx.get("slot"),
        "fee_sol": meta.get("fee", 0) / LAMPORTS_PER_SOL,
        "compute_units": meta.get("computeUnitsConsumed"),
        "fee_payer": fee_payer,
        "signers": signers,
        "instructions": instructions,
        "programs": programs,
        "sol_changes": sorted(sol_changes, key=lambda c: c["change_sol"]),
        "token_changes": sorted(token_changes, key=lambda c: c["change"]),
        "inner_instruction_groups": len(meta.get("innerInstructions") or []),
    }


# ---------- explanation ----------
def explain_rule_based(s: dict, level: str = "beginner") -> str:
    lines = []
    if s["status"] == "success":
        lines.append(f"This transaction succeeded on {s['time']}.")
    else:
        lines.append(f"This transaction FAILED on {s['time']}. Nothing it tried to do took effect, but the fee was still charged. Error: {s['error']}")
    lines.append(f"It was signed by {', '.join(short(x) for x in s['signers']) or 'unknown'} "
                 f"and {short(s['fee_payer'])} paid a network fee of {s['fee_sol']:.6f} SOL.")
    if s["instructions"]:
        lines.append("\nWhat it did, step by step:")
        lines += [f"  {i}. {ix['description']}" for i, ix in enumerate(s["instructions"], 1)]
    if s["sol_changes"]:
        lines.append("\nSOL balance changes:")
        lines += [f"  • {short(c['account'])}: {c['change_sol']:+.6f} SOL" for c in s["sol_changes"]]
    if s["token_changes"]:
        lines.append("\nToken balance changes:")
        lines += [f"  • {short(c['owner'])}: {c['change']:+g} of mint {short(c['mint'])}" for c in s["token_changes"]]
    if level == "developer":
        lines.append("\nPrograms invoked:")
        lines += [f"  • {p['name']} ({p['id']})" for p in s["programs"]]
        lines.append(f"\nCompute units used: {s['compute_units']}, slot: {s['slot']}, inner instruction groups: {s['inner_instruction_groups']}")
    else:
        lines.append("\nPrograms involved (a program is Solana's word for a smart contract):")
        lines += [f"  • {p['name']}: {p['about'] or 'no description in our built-in list.'}" for p in s["programs"]]
    return "\n".join(lines)


def explain_with_llm(s: dict, level: str = "beginner", api_key: str | None = None) -> str:
    """Ask Claude to explain the parsed summary. Raises SolScribeError on any failure."""
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SolScribeError("No ANTHROPIC_API_KEY set.")
    audience = ("a complete beginner who has never used a blockchain. Avoid jargon, define any term you must use."
                if level == "beginner" else
                "a developer new to Solana. Mention programs, instruction types, accounts and compute usage, and what to look up next.")
    prompt = (
        f"Explain this Solana transaction to {audience}\n"
        "Rules: use ONLY the facts in the JSON below; never invent amounts, names or intent; if something is unknown, say so. "
        "Keep it under 180 words, then add one line starting 'Why it matters:'.\n\n"
        f"{json.dumps(s, indent=2, default=str)}"
    )
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": os.environ.get("SOLSCRIBE_MODEL", "claude-sonnet-5-5"), "max_tokens": 600,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=45,
        )
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text").strip()
    except (requests.RequestException, ValueError) as e:
        raise SolScribeError(f"AI explanation failed: {e}") from e


def explain(s: dict, level: str = "beginner", use_ai: bool = True, api_key: str | None = None) -> tuple[str, str]:
    """Return (text, source) where source is 'ai' or 'rules'. Always falls back to rules."""
    if use_ai and (api_key or os.environ.get("ANTHROPIC_API_KEY")):
        try:
            return explain_with_llm(s, level, api_key), "ai"
        except SolScribeError:
            pass
    return explain_rule_based(s, level), "rules"
