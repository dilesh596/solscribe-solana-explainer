import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import core


def test_detect_input_type():
    assert core.detect_input_type("11111111111111111111111111111111") == "address"
    assert core.detect_input_type("5" * 88) == "signature"
    assert core.detect_input_type("hello world") == "invalid"
    assert core.detect_input_type("") == "invalid"
    assert core.detect_input_type("0OIl" * 10) == "invalid"  # chars not in base58


def test_short():
    assert core.short("ABCDEFGHIJKLMNOP") == "ABCD…MNOP"
    assert core.short(None) == "?"


def test_summarize_sample():
    s = core.summarize(core.load_sample())
    assert s["status"] == "success"
    assert abs(s["fee_sol"] - 0.000005) < 1e-12
    assert len(s["instructions"]) == 3
    assert "Sent 0.5 SOL" in s["instructions"][0]["description"]
    assert "10 tokens" in s["instructions"][1]["description"]
    assert "Rent split for November" in s["instructions"][2]["description"]
    changes = {c["account"][:5]: c["change_sol"] for c in s["sol_changes"]}
    assert abs(changes["Alice"] - (-0.500005)) < 1e-9
    assert abs(changes["BobDe"] - 0.5) < 1e-9
    toks = {c["owner"][:5]: c["change"] for c in s["token_changes"]}
    assert toks["Alice"] == -10 and toks["BobDe"] == 10
    assert [p["name"] for p in s["programs"]] == ["System Program", "SPL Token Program", "Memo Program"]


def test_failed_tx_and_unknown_program():
    tx = core.load_sample()
    tx["meta"]["err"] = {"InstructionError": [0, "Custom"]}
    tx["transaction"]["message"]["instructions"].append(
        {"programId": "Unknown1111111111111111111111111111111111", "accounts": [], "data": "abc"})
    s = core.summarize(tx)
    assert s["status"] == "failed"
    assert "FAILED" in core.explain_rule_based(s)
    assert "Unknown program" in s["instructions"][-1]["program"]


def test_explain_falls_back_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    text, source = core.explain(core.summarize(core.load_sample()), "developer", use_ai=True)
    assert source == "rules" and "Programs invoked" in text
