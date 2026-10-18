"""MS-b over digests made by hand: a group shows its first SUPPORTED member and keeps the others'
status under it (MS-D §7, review B5); one relation once is settled on what the bound left (§6,
review B4); a board item's link said within what the claim graph holds (§6, I3)."""

from __future__ import annotations

from calliope.agent.digest import STEPS, bounded, grouped, settle, size
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
    shown = bounded(d, 10_000)
    settle(d["board"], shown)
    assert shown["claims"] == []  # the item carrying it is shown: once, there


def test_a_linked_item_the_bound_moved_out_leaves_its_claim_listed_and_named() -> None:
    """Review B4: never neither. Step 0 moves a plain item out before a linked one; when it must
    move the linked one too, the claim stays listed and the item is named by its ref."""

    d = _digest_with_a_linked_item()
    for item in d["board"]["changes"]:
        item["kind"] = "weakness"  # none kept by step 0 (BOARD_KEEP)
    d["board"]["changes"] = d["board"]["changes"][:2]  # b1 (linked), b2 (plain)
    one = bounded(d, size(d) - 150)  # one item out: the plain one
    settle(d["board"], one)
    assert [c["ref"] for c in one["board"]["changes"]] == ["b1"] and one["claims"] == []
    both = bounded(d, size(d) - 300)  # both out
    settle(d["board"], both)
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
