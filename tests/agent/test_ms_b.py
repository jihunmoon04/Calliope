"""MS-b over digests made by hand: a group shows its first SUPPORTED member and keeps the others'
status under it (MS-D §7, review B5); one relation once is settled on what the bound left (§6,
review B4); a board item's link said within what the claim graph holds (§6, I3)."""

from __future__ import annotations

from calliope.agent.digest import STEPS, DigestTooLarge, bounded, grouped, size
from calliope.agent.remarks import held_proves, link_remark


def _claim(ref: str, template: str, status: str) -> dict:
    return {"ref": ref, "template": template, "role": "comparison", "part": "comparison",
            "status": status, "scope": [], "proves": f"[{template}]"}  # fmt: skip


def test_a_group_shows_its_first_supported_member_and_keeps_the_others_status() -> None:
    claims = [_claim("c1", "better_move_v1", "inconclusive"),
              _claim("c2", "missed_gain_v1", "supported"),
              _claim("c3", "better_alternative_v1", "supported"),
              _claim("c4", "material_loss_v2", "supported")]  # fmt: skip
    out = grouped(claims)
    assert [c["ref"] for c in out] == ["c2", "c4"]
    assert out[0]["also"] == [
        {"ref": "c1", "template": "better_move_v1", "status": "inconclusive",
         "proves": "[better_move_v1]"},
        {"ref": "c3", "template": "better_alternative_v1", "status": "supported",
         "proves": "[better_alternative_v1]"},
    ]  # fmt: skip
    only = grouped([_claim("c1", "better_move_v1", "inconclusive"),
                    _claim("c3", "better_alternative_v1", "inconclusive")])  # fmt: skip
    assert [c["ref"] for c in only] == ["c1"]  # none SUPPORTED: the first INCONCLUSIVE
    assert grouped([_claim("c1", "better_move_v1", "supported")])[0].get("also") is None


def _digest_with_a_linked_item() -> dict:
    item = {"kind": "lost_defence", "ref": "b1", "part": "reason", "owner": "black",
            "good_for": "white", "proves": "x" * 200, "propositions": [],
            "leads_to": {"claim": "c9", "template": "removed_defender_v2"}}  # fmt: skip
    plain = {"kind": "lost_defence", "ref": "b2", "part": "reason", "owner": "black",
             "good_for": "white", "proves": "y" * 200, "propositions": []}  # fmt: skip
    extra = {"kind": "lost_defence", "ref": "b3", "part": "reason", "owner": "black",
             "good_for": "white", "proves": "z" * 200, "propositions": []}  # fmt: skip
    return {
        "judgement": "j1", "evaluation": {}, "lines": {"played": {"ref": "s1", "pv": "a b c d"}},
        "board": {"v": "board_v2", "mover": "black", "changes": [item, plain, extra]},
        "claims": [_claim("c9", "removed_defender_v2", "supported")],
        "not_shown": {"refuted": [], "others": [], "named": [], "steps": [], "counts": {},
                      "capped": {}},
    }  # fmt: skip


def test_a_claim_leaves_the_list_only_under_a_shown_item() -> None:
    d = _digest_with_a_linked_item()
    shown = bounded(d, 10_000, built=d["board"])
    assert shown["claims"] == []  # the item carrying it is shown: once, there


def test_a_linked_item_the_bound_moved_out_leaves_its_claim_listed_and_named() -> None:
    """Review B4: never neither. Step 0 moves a plain item out before a linked one; when it must
    move the linked one too, the claim stays listed and the item is named by its ref."""

    d = _digest_with_a_linked_item()
    for item in d["board"]["changes"]:
        item["kind"] = "weakness"  # none kept by step 0 (BOARD_KEEP)
    d["board"]["changes"] = d["board"]["changes"][:2]  # b1 (linked), b2 (plain)
    base = size(bounded(d, 10**6, built=d["board"]))  # settled: the claim under its item
    one = bounded(d, base - 150, built=d["board"])  # one item out: the plain one
    assert [c["ref"] for c in one["board"]["changes"]] == ["b1"] and one["claims"] == []
    both = bounded(d, base - 300, built=d["board"])  # both out: the claim listed again
    assert both["board"]["changes"] == []
    assert [c["ref"] for c in both["claims"]] == ["c9"]
    assert {"board": "weakness", "ref": "b1", "leads_to": "c9"} in both["not_shown"]["named"]


def test_the_steps_begin_with_the_board_and_the_groups() -> None:
    assert STEPS[:2] == ("board", "also") and "text" not in STEPS


def test_a_link_says_what_the_graph_holds_and_no_more() -> None:
    explains = link_remark({"link": "explains", "to_template": "material_loss_v2"})
    assert "설명한다" in explains and "물질 손실" in explains
    associated = link_remark({"link": "associated_with", "to_template": "material_loss_v2",
                              "did": "configuration"})  # fmt: skip
    assert "함께 나온다" in associated and "원인으로 확인되지는 않음" in associated
    assert "배치일 뿐" in associated and "설명한다" not in associated
    assert link_remark({"claim": "c1"}) == ""
    held = held_proves("black", "31...Qf6", "흑 폰(f5)", 1)
    assert "전에도 뒤에도" in held and "—" not in held and "1점" in held


def test_the_settled_digest_is_within_the_bound() -> None:
    """MS-b review B2: naming a moved-out linked item costs characters; the bound counts them."""

    d = _digest_with_a_linked_item()
    for item in d["board"]["changes"]:
        item["kind"] = "weakness"
    for limit in range(size(d) - 50, size(d) - 700, -25):
        try:
            out = bounded(d, limit, built=d["board"])
        except DigestTooLarge:  # too small for every ref: an error, never a cut
            out = None
        assert out is None or size(out) <= limit, limit


def test_board_handles_are_counted_by_the_handle_limit(tmp_path) -> None:
    """MS-b review B1: the `b` handles go through the session's own path, so `max_handles` holds
    for them as for every other handle."""

    import pytest
    from agent_helpers import GAME, session

    from calliope.agent import Limits
    from calliope.agent.budget import BudgetError

    free = session(tmp_path / "free")
    game = free.open_game(pgn=GAME, plies="1-2")["game"]
    opened = len(free.handles)  # the analyses' handles, served when the plies were analysed
    d = free.ply(game, 2)
    boards = [c["ref"] for c in d["board"]["changes"]]
    assert boards and all(r.startswith("b") for r in boards)
    free.close()
    # room for every handle but the last board item's: the board is refused, never over the limit
    limit = opened + len(boards) - 1
    tight = session(tmp_path / "tight", Limits(max_handles=limit))
    game = tight.open_game(pgn=GAME, plies="1-2")["game"]
    with pytest.raises(BudgetError, match="handles"):
        tight.ply(game, 2)
    assert len(tight.handles) <= limit
    tight.close()


def test_a_proves_too_long_to_show_whole_is_none(monkeypatch) -> None:
    """MS-b re-review N3: never a cut `proves` whose tokens go past what it shows."""

    from calliope.agent import remarks

    mate = {"template": "mate_allowed_v1",
            "findings": [{"type": "MateFinding", "moves": 4, "mating_move": {
                "uci": "f3g5", "fen": "r1b1r2Q/pp3k2/3n2p1/4R3/6P1/P4N1P/1q4PK/3R4 w - - 3 30"}}],
            "effective_scopes": [{"quantifier": "specific_line"}]}  # fmt: skip
    text, tokens = remarks.claim_remark(mate, "black")
    assert len(text) <= remarks.PROVES_CAP and tokens.integers == {4}
    monkeypatch.setattr(remarks, "PROVES_CAP", len(text) - 1)
    assert remarks.claim_remark(mate, "black") is None
    assert remarks.claim_proves(mate, "black") is None
