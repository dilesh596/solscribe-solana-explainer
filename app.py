"""SolScribe: Streamlit app. Run with:  streamlit run app.py"""
import streamlit as st

import core

st.set_page_config(page_title="SolScribe", page_icon="📜", layout="wide")
st.title("📜 SolScribe")
st.caption("Paste any Solana transaction or wallet. Get a plain-English explanation. Read-only: no wallet or keys needed.")

with st.sidebar:
    st.header("Settings")
    network = st.selectbox("Network", list(core.NETWORKS), index=0)
    level = st.radio("Explain for a…", ["beginner", "developer"])
    use_ai = st.toggle("Use Claude for the explanation", value=True)
    api_key = st.text_input("Anthropic API key (optional)", type="password",
                            help="Without a key, SolScribe uses its built-in rule-based explainer.")
    st.markdown("---")
    st.markdown("**Try it offline:** use the demo button on the Explain tab.")

tab_tx, tab_wallet, tab_learn = st.tabs(["Explain a transaction", "Wallet overview", "Learn Solana"])


def show(summary: dict):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", summary["status"].upper())
    c2.metric("Fee (SOL)", f"{summary['fee_sol']:.6f}")
    c3.metric("Instructions", len(summary["instructions"]))
    c4.metric("Time", summary["time"])
    with st.spinner("Writing explanation…"):
        text, source = core.explain(summary, level, use_ai, api_key or None)
    st.subheader("Explanation " + ("(AI)" if source == "ai" else "(rule-based)"))
    st.text(text) if source == "rules" else st.write(text)
    left, right = st.columns(2)
    with left:
        st.subheader("Money movement")
        if summary["sol_changes"]:
            st.dataframe([{"account": core.short(c["account"]), "SOL change": f"{c['change_sol']:+.6f}"}
                          for c in summary["sol_changes"]])
        if summary["token_changes"]:
            st.dataframe([{"owner": core.short(c["owner"]), "mint": core.short(c["mint"]), "change": f"{c['change']:+g}"}
                          for c in summary["token_changes"]])
    with right:
        st.subheader("Programs involved")
        st.dataframe([{"program": p["name"], "what it is": p["about"]} for p in summary["programs"]])
    with st.expander("Raw parsed summary (JSON)"):
        st.json(summary)


with tab_tx:
    sig = st.text_input("Transaction signature")
    b1, b2 = st.columns([1, 1])
    go = b1.button("Explain", type="primary")
    demo = b2.button("Load offline demo")
    try:
        if demo:
            show(core.summarize(core.load_sample()))
        elif go:
            if core.detect_input_type(sig) != "signature":
                st.error("That doesn't look like a transaction signature (expected ~88 base58 characters).")
            else:
                with st.spinner("Fetching from Solana…"):
                    tx = core.fetch_transaction(sig.strip(), network)
                show(core.summarize(tx))
    except core.SolScribeError as e:
        st.error(str(e))

with tab_wallet:
    addr = st.text_input("Wallet address")
    if st.button("Look up wallet"):
        try:
            if core.detect_input_type(addr) != "address":
                st.error("That doesn't look like a Solana address (32–44 base58 characters).")
            else:
                st.session_state["bal"] = core.fetch_balance_sol(addr.strip(), network)
                st.session_state["sigs"] = core.fetch_recent_signatures(addr.strip(), 10, network)
        except core.SolScribeError as e:
            st.error(str(e))
    if "bal" in st.session_state:
        st.metric(f"Balance on {network}", f"{st.session_state['bal']:.4f} SOL")
        sigs = st.session_state.get("sigs", [])
        if sigs:
            st.dataframe([{"signature": s["signature"], "status": "failed" if s.get("err") else "ok"} for s in sigs])
            st.info("Copy a signature into the first tab to get the explanation.")
        else:
            st.write("No recent transactions found.")

with tab_learn:
    st.subheader("Solana in 60 seconds")
    st.markdown("""
- **Account**: everything on Solana is an account: wallets, tokens, programs.
- **Lamport**: the smallest unit of SOL. 1 SOL = 1,000,000,000 lamports.
- **Transaction**: a bundle of instructions signed by one or more wallets. All succeed or none do.
- **Instruction**: one action, such as "transfer 0.5 SOL", sent to a specific program.
- **Program**: Solana's word for a smart contract.
- **Signature**: the unique ID of a transaction, which you can look up on any explorer.
- **Fee**: a tiny network fee, paid even when a transaction fails.
- **Devnet**: a practice network where SOL is free and worthless. Safe for learning.
""")
    st.subheader("Known programs SolScribe recognises")
    st.dataframe([{"program": v[0], "what it is": v[1]} for v in core.KNOWN_PROGRAMS.values()])
