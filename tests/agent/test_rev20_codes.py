"""Harness rev. 20: atomic `b`/`m` handle codes, lightweight submission, and `harness_frames_v7`."""

from __future__ import annotations

import json
from types import SimpleNamespace

import anyio
from agent_helpers import GAME, session

from calliope.agent.record import HANDLE, identity_fields
from tools.rx import frames, harness
from tools.rx import model as rx_model
from tools.rx import run as rx_run


def _hex24(tag: str) -> str:
    return (tag * 24)[:24]


def test_material_handle_identity_explore_and_compare_lines(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CALLIOPE_STANDING_NUMBERS", "1")
    s = session(tmp_path)
    try:
        game = s.open_game(pgn=GAME, plies="1-3")["game"]
        d3 = s.ply(game, 3)

        ex = s.explore(game, {"ply": 2, "at": "after"}, ["Nf3", "Nc6"])
        m_ref = ex["ledger"]["ref"]
        assert isinstance(m_ref, str) and m_ref.startswith("m") and HANDLE.fullmatch(m_ref)

        det = s.detail(game, m_ref)
        assert det["kind"] == "material"
        assert det["item"]["line"] == ex["ref"]
        assert det["item"]["balance"] == ex["ledger"]["net"][ex["ledger"]["plies"][0]["side"]]

        addr = {
            "from": ["e2e4", "d7d5"],
            "moves": ["g1f3", "b8c6"],
            "by": "agent",
            "start": 0,
            "end": 2,
            "side": "white",
            "origins": ["agent", "agent"],
        }
        assert identity_fields("material", "g", {"kind": "facts_tree"}, addr) == identity_fields(
            "material", "g", {"kind": "facts_tree"}, dict(addr)
        )
        assert identity_fields("material", "g", {}, addr) != identity_fields(
            "material", "g", {}, addr | {"origins": ["agent", "search"]}
        )
        # Same moves with different ply origins get distinct `m` handles.
        g_obj = s.game(game)
        m_search = s._serve_material(
            g_obj,
            ex["ref"],
            tuple(ex["start"]["from_root"]),
            ex["end"]["from_root"][len(ex["start"]["from_root"]) :],
            "agent",
            {
                **ex["ledger"],
                "plies": [
                    ex["ledger"]["plies"][0],
                    {**ex["ledger"]["plies"][1], "source": "search"},
                ],
            },
            {},
        )
        assert m_search and m_search != m_ref

        cmp = s.compare_lines(game, 3, length=3, candidates=["exd5", "Nc3"])
        for name, line in cmp["lines"].items():
            if name == "candidates":
                for cand in line:
                    assert set(cand["ledger"]) == {"captured", "net", "standing", "end"}
                    if cand["moves"]:
                        assert cand["material_ref"].startswith("m")
                        assert HANDLE.fullmatch(cand["material_ref"])
            else:
                assert set(line["ledger"]) == {"captured", "net", "standing", "end"}
                if line["moves"]:
                    assert line["material_ref"].startswith("m")
                    assert HANDLE.fullmatch(line["material_ref"])

        end_stand = ex["ledger"]["standing"]["end"]["white_minus_black"]
        answer = s.submit_commentary(
            game,
            ply=3,
            agent={"name": "t"},
            sentences=[
                {"text": "이 수는 판정을 받는다.", "class": "sourced", "cites": [d3["judgement"]]},
                {
                    "text": f"후속 진행 끝에서 백 기준 형세는 {end_stand}점이다.",
                    "class": "sourced",
                    "cites": [m_ref],
                },
            ],
        )
        assert answer["accepted"], answer
    finally:
        s.close()


def test_squares_and_facts_atomic_b_handles_keep_f_refused(tmp_path) -> None:
    s = session(tmp_path)
    try:
        game = s.open_game(pgn=GAME, plies="1-3")["game"]
        d3 = s.ply(game, 3)

        sq = s.squares(game, {"ply": 2, "at": "after"}, ["d5", "a3"])
        by_sq = {e["square"]: e for e in sq["squares"]}
        d5_ref = by_sq["d5"].get("ref")
        assert isinstance(d5_ref, str) and d5_ref.startswith("b") and HANDLE.fullmatch(d5_ref)
        assert "ref" not in by_sq["a3"]

        det = s.detail(game, d5_ref)
        assert det["kind"] == "board_item"
        assert det["item"]["entry"]["square"] == "d5"
        assert det["item"]["propositions"]
        assert "changed_by_move" not in det["item"]["entry"]

        # Same square queried by `from_root` returns the same `b` handle cleanly without drift.
        sq_root = s.squares(game, {"from_root": ["e2e4", "d7d5"]}, ["d5"])
        assert sq_root["squares"][0]["ref"] == d5_ref
        assert "changed_by_move" in by_sq["d5"]
        assert "changed_by_move" not in sq_root["squares"][0]

        f_ans = s.facts(game, {"ply": 2, "at": "after"}, families=["status", "pawns", "patterns"])
        citable = f_ans.get("citable") or []
        assert citable and all(
            isinstance(c.get("ref"), str) and c["ref"].startswith("b") for c in citable
        )

        # Standalone `f` handle remains refused; atomic `b` handle is accepted.
        f_ref = f_ans["families"]["status"]["ref"]
        bad = s.submit_commentary(
            game,
            ply=3,
            agent={"name": "t"},
            sentences=[
                {"text": "판정.", "class": "sourced", "cites": [d3["judgement"]]},
                {"text": "상태 기록.", "class": "sourced", "cites": [f_ref]},
            ],
        )
        assert not bad["accepted"]

        good = s.submit_commentary(
            game,
            ply=3,
            agent={"name": "t"},
            sentences=[
                {"text": "판정.", "class": "sourced", "cites": [d3["judgement"]]},
                {"text": "d5 폰의 관계.", "class": "sourced", "cites": [d5_ref]},
            ],
        )
        assert good["accepted"], good
    finally:
        s.close()


def test_frames_v7_m_handle_and_search_backed_segment_slicing() -> None:
    x_ref = f"x1.{_hex24('a')}"
    m_ref = f"m1.{_hex24('b')}"
    book = {
        "plies": [
            {"ply": 1, "side": "white", "san": "exd5", "source": "agent", "standing_white": 3},
            {"ply": 2, "side": "black", "san": "Nxd5", "source": "agent", "standing_white": -1},
            {"ply": 3, "side": "white", "san": "Nf3", "source": "search", "standing_white": -1},
        ],
        "net": {"white": 0, "black": -3},
        "standing": {
            "start": {"white_minus_black": 2},
            "end": {"white_minus_black": -1, "leader_at_end": "black"},
        },
        "captured": {"by_white": [], "by_black": []},
    }
    m_item = {"line": x_ref, "from": 0, "to": 2, "side": "black", "balance": -3, "ledger": book}
    records = {m_ref: ("material", m_item)}

    assert m_ref in frames.refs_needed(
        {"sentences": [{"text": "이 수순에서 흑은 3점을 잃는다.", "cites": [m_ref]}]}
    )

    ok = frames.check(
        {"sentences": [{"text": "이 수순에서 흑은 3점을 잃는다.", "cites": [m_ref]}]},
        records,
        frames.FRAMES_V7,
    )
    assert ok["held"] == [] and ok["uncheckable"] == []

    # Citing both `m1` and its underlying `x1` must not trigger duplicate-line `uncheckable`.
    both = frames.check(
        {"sentences": [{"text": "이 수순에서 흑은 3점을 잃는다.", "cites": [m_ref, x_ref]}]},
        records | {x_ref: ("explored_line", {"ledger": book})},
        frames.FRAMES_V7,
    )
    assert both["held"] == [] and both["uncheckable"] == []

    bad = frames.check(
        {"sentences": [{"text": "이 수순에서 백이 3점 앞선다.", "cites": [m_ref]}]},
        records,
        frames.FRAMES_V7,
    )
    assert [h["rule"] for h in bad["held"]] == ["F1"]

    # F4 (crossover) and F5 (no_change) also hold on `m` handles alone and with `x`.
    f5_solo = frames.check(
        {"sentences": [{"text": "물질 변화가 없다.", "cites": [m_ref]}]},
        records,
        frames.FRAMES_V7,
    )
    f5_both = frames.check(
        {"sentences": [{"text": "물질 변화가 없다.", "cites": [m_ref, x_ref]}]},
        records | {x_ref: ("explored_line", {"ledger": book})},
        frames.FRAMES_V7,
    )
    f4_solo = frames.check(
        {"sentences": [{"text": "우위가 백 쪽으로 넘어간다.", "cites": [m_ref]}]},
        records,
        frames.FRAMES_V7,
    )
    f4_both = frames.check(
        {"sentences": [{"text": "우위가 백 쪽으로 넘어간다.", "cites": [m_ref, x_ref]}]},
        records | {x_ref: ("explored_line", {"ledger": book})},
        frames.FRAMES_V7,
    )
    assert [h["rule"] for h in f5_solo["held"]] == ["F5"]
    assert [h["rule"] for h in f5_both["held"]] == ["F5"]
    assert [h["rule"] for h in f4_solo["held"]] == ["F4"]
    assert [h["rule"] for h in f4_both["held"]] == ["F4"]

    # Ledger-less comparison `x_ref` + `m_ref` still checks F1/F4/F5 via `m_ref`'s ledger.
    no_ledger_x = {"plies": book["plies"][:2], "start": {"fen": "4k3/8/8/8/8/8/8/4K3 w - - 0 1"}}
    for text, expected_rule in (
        ("이 수순에서 백이 3점 앞선다.", "F1"),
        ("우위가 백 쪽으로 넘어간다.", "F4"),
        ("물질 변화가 없다.", "F5"),
    ):
        res = frames.check(
            {"sentences": [{"text": text, "cites": [m_ref, x_ref]}]},
            records | {x_ref: ("explored_line", no_ledger_x)},
            frames.FRAMES_V7,
        )
        assert [h["rule"] for h in res["held"]] == [expected_rule]

    # Direct `j` handle citations run F3 grade checks in v7.
    j_ref = f"j1.{_hex24('9')}"
    j_rec = {j_ref: ("judgement", {"grade": "blunder", "label": None, "move": {"san": "exd5"}})}
    assert frames.judgements_needed(
        {"sentences": [{"text": "이 수는 실수다.", "cites": [j_ref]}]}
    ) == {j_ref}
    f3_bad = frames.check(
        {"sentences": [{"text": "이 수는 실수다.", "cites": [j_ref]}]},
        j_rec,
        frames.FRAMES_V7,
    )
    f3_ok = frames.check(
        {"sentences": [{"text": "이 수는 블런더다.", "cites": [j_ref]}]},
        j_rec,
        frames.FRAMES_V7,
    )
    assert [h["rule"] for h in f3_bad["held"]] == ["F3"]
    assert f3_ok["held"] == []

    # Segment 0..2 has only `agent` plies; trailing ply 3 is `search`, so `_search_backed` is False.
    assert frames._search_backed([], [m_ref], records) is False
    search_m = m_item | {
        "ledger": book | {"plies": [{**book["plies"][0], "source": "search"}, *book["plies"][1:]]}
    }
    assert frames._search_backed([], [m_ref], {m_ref: ("material", search_m)}) is True


def test_rev20_prompts_tools_check_and_render() -> None:
    msgs = harness.ALL_MESSAGES[20]
    fmt_args = {
        "write": {"move": "2.exd5", "how": "통과했어", "facts": "FACTS", "checked": "CHECKED", "digest": "DIGEST"},
        "task": {"game_id": "g1", "moments": "2.exd5"},
        "facts": {"move": "2.exd5"},
        "retry": {"move": "2.exd5", "problems": "p"},
        "check": {"move": "2.exd5", "problems": "p"},
        "submit": {"move": "2.exd5", "how": "통과했어"},
        "gate": {"ply": "3"},
        "unsubmitted": {"move": "2.exd5", "ply": 3},
        "held": {"problems": "p"},
        "story": {"story": "s"},
        "notes": {"notes": "n"},
        "refused_detail": {"tool": "detail", "size": 100},
        "refused_length": {"tool": "explore", "size": 100},
        "refused_overview": {"tool": "game_overview", "size": 100},
        "refused_facts": {"tool": "facts", "size": 100},
        "refused_other": {"tool": "detail", "size": 100},
        "tier1_task": {"count": 1, "game_id": "g1", "moves": "3.c4 (ply 5)"},
        "tier1_story": {"story": "s"},
        "tier1_digest": {"move": "3.c4", "ply": 5, "digest": "d"},
        "tier1_gate": {"ply": "5"},
        "tier1_unsubmitted": {"ply": "5"},
        "tier1_refused": {"tool": "detail", "size": 100},
    }
    for key, kwargs in fmt_args.items():
        assert isinstance(msgs[key].format(**kwargs), str)

    base_tools = [
        {"type": "function", "function": {"name": "detail", "parameters": {"properties": {"ref": {}}}}},
        {
            "type": "function",
            "function": {
                "name": "submit_commentary",
                "parameters": {
                    "required": ["game", "agent", "propositions", "sentences"],
                    "properties": {
                        "game": {},
                        "agent": {},
                        "propositions": {},
                        "states": {},
                        "sentences": {},
                    },
                },
            },
        },
    ]
    t2 = harness._codes_only_tools(base_tools, tier=2)
    t1 = harness._codes_only_tools(base_tools, tier=1)
    assert t2[0] == base_tools[0]
    assert set(t2[1]["function"]["parameters"]["properties"]) == {"ply", "sentences"}
    assert set(t1[1]["function"]["parameters"]["properties"]) == {"items"}

    b_ref = f"b3.{_hex24('c')}"
    f_ref = f"f1.{_hex24('d')}"
    x_ref = f"x1.{_hex24('e')}"
    m_ref = f"m1.{_hex24('f')}"
    s_ref = f"s2.{_hex24('1')}"
    k_ref = f"k1.{_hex24('2')}"

    board_entry = {
        "square": "f7",
        "piece": "black pawn on f7",
        "attackers": [{"piece": "Ng5"}],
        "defenders": [{"piece": "Kg8"}],
        "absolutely_pinned": {"pinner": "Bb5"},
    }
    verdict, _ = harness.check_claim(
        {"kind": "defenders", "ref": b_ref, "square": "f7", "value": ["Kg8"]},
        "board_item",
        {"entry": board_entry},
    )
    assert verdict == "agrees"
    wrong_sq, _ = harness.check_claim(
        {"kind": "defenders", "ref": b_ref, "square": "e7", "value": ["Kg8"]},
        "board_item",
        {"entry": board_entry},
    )
    assert wrong_sq == "unbacked"

    line_summary = harness._summary(
        "explored_line",
        {
            "start": {"fen": "4k3/8/8/8/8/8/8/4K3 w - - 0 1"},
            "plies": [],
            "ledger": {
                "ref": m_ref,
                "plies": [],
                "net": {"white": 0, "black": 0},
                "standing": {"start": {"white_minus_black": 0}, "end": {"white_minus_black": 0}},
                "captured": {"by_white": [], "by_black": []},
            },
        },
        {"kind": "line_net", "ref": x_ref},
    )
    assert line_summary["material_ref"] == m_ref

    checked = [
        {"n": 1, "claim": {"kind": "line_net", "ref": x_ref}, "record": line_summary},
        {
            "n": 2,
            "claim": {"kind": "defenders", "ref": f_ref, "square": "f7"},
            "record": board_entry,
        },
        {
            "n": 3,
            "claim": {"kind": "better_for_mover", "ref": k_ref},
            "record": [
                {
                    "move": "1...e5",
                    "rank": 1,
                    "for_mover": "+0.45",
                    "vs_played": "+0.20",
                    "white_view": "-0.45",
                    "score_ref": s_ref,
                }
            ],
        },
    ]
    legacy = harness.render_checked(checked)
    assert x_ref in legacy and f_ref in legacy and "물질 코드" not in legacy
    assert "두는 쪽 기준 순위 1. 1...e5 (+0.45, 둔 수 대비 +0.20)" in legacy
    assert "Ng5" in legacy and "Kg8" in legacy and "Bb5" in legacy
    coded = harness.render_checked(
        checked,
        codes_only=True,
        square_refs={("posA", "f7"): b_ref},
        ref_positions={f_ref: "posA"},
    )
    assert "물질 코드: m1" in coded
    assert "인용코드: b3" in coded
    assert "백 기준 -0.45 [코드: s2]" in coded and "후보 평가:" in coded
    assert "+0.45" not in coded and "+0.20" not in coded and "순위 1." not in coded
    assert "백 나이트 g5" in coded and "백 킹 g8" in coded and "백 비숍 b5" in coded
    assert "Ng5" not in coded and "Kg8" not in coded and "Bb5" not in coded
    assert x_ref not in coded and b_ref not in coded

    # Rendered square prose uses square tokens that pass S3 sentence checks under the `b` handle.
    from calliope.agent.sentences import Allowed, check_sentences

    allowed_b = Allowed()
    allowed_b.squares |= {"f7", "g5", "g8", "b5"}
    sq_problems = check_sentences(
        "ko",
        [
            {
                "text": "f7 칸의 흑 폰을 백 나이트 g5가 공격하고 백 킹 g8이 수비한다.",
                "class": "sourced",
                "cites": ["b3"],
            }
        ],
        {"b3": allowed_b},
    )
    assert sq_problems == []

    # Cross-position square code is omitted; comparison material_ref still surfaces via line_materials.
    f_other = f"f2.{_hex24('9')}"
    cross_checked = [
        {"n": 1, "claim": {"kind": "line_net", "ref": x_ref}, "record": {"moves": ["e4"], "net": {"white": 0, "black": 0}, "standing": {"start": {"white_minus_black": 0}, "end": {"white_minus_black": 0, "leader_at_end": "level"}}, "captured": {"by_white": [], "by_black": []}}},
        {"n": 2, "claim": {"kind": "defenders", "ref": f_other, "square": "f7"}, "record": board_entry},
    ]
    cross = harness.render_checked(
        cross_checked,
        codes_only=True,
        square_refs={(f_ref, "f7"): b_ref, (("e2e4",), "f7"): b_ref},
        ref_positions={f_ref: ("e2e4",), f_other: ("d2d4",)},
        line_materials={x_ref: m_ref},
    )
    assert "물질 코드: m1" in cross
    assert "인용코드: b3" not in cross and "f… 코드는 단독 인용 불가" in cross


def _reply(content=None, calls=()):
    msg = {"content": content}
    if calls:
        msg["tool_calls"] = [
            {"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}}
            for i, (n, a) in enumerate(calls)
        ]
    return rx_model.Reply(
        message=msg, usage={"input_tokens": 10, "output_tokens": 5, "cost": 0.001}, body_fields=[]
    )


class _Model:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        self.tools = []

    def count(self, messages, tools, tool_choice=None):
        return 500

    def complete(self, messages, tools, tool_choice=None):
        self.requests.append(json.loads(json.dumps(messages)))
        self.tools.append([t["function"] for t in tools or []])
        return self.replies.pop(0)


def test_rev20_gate_and_loop_end_to_end(tmp_path, monkeypatch) -> None:
    info20 = rx_run._harness_info(
        SimpleNamespace(arm="H", harness_revision=20, harness_guide=None)
    )
    info19 = rx_run._harness_info(
        SimpleNamespace(arm="H", harness_revision=19, harness_guide=None)
    )
    assert info20["harness_codes_only"] is True
    assert info20["harness_frames"] == frames.FRAMES_V7
    assert info20["harness_guide"] == "harness_guide_v4"
    assert info20["harness_tier1"] == "harness_tier1_v5"
    assert info19["harness_codes_only"] is False

    # Wrong explicit game ID stays blocked even in codes-only mode.
    gate = harness.Gate(None, harness.Game(GAME), None, "g")
    gate.codes_only = True
    gate.phase, gate.current_ply = "submit", 3
    assert gate.allows({"game": "wrong", "ply": 3, "sentences": []})[0] is False

    # Position-exact square ref mapping and compare_lines `material_ref` capture in Gate._learn.
    f_pos_a = f"f8.{_hex24('a')}"
    f_pos_b = f"f9.{_hex24('b')}"
    b_pos_b = f"b9.{_hex24('c')}"
    cmp_x = f"x9.{_hex24('d')}"
    cmp_m = f"m9.{_hex24('e')}"
    gate._learn(
        "facts",
        {},
        json.dumps({"position": {"from_root": ["e2e4"]}, "families": {"pieces": {"ref": f_pos_a}}}),
    )
    gate._learn(
        "squares",
        {},
        json.dumps(
            {
                "position": {"from_root": ["d2d4"]},
                "refs": {"pieces": f_pos_b},
                "squares": [{"square": "d5", "ref": b_pos_b}],
            }
        ),
    )
    gate._learn(
        "compare_lines",
        {},
        json.dumps(
            {
                "lines": {
                    "played": {"ref": cmp_x, "material_ref": cmp_m},
                    "candidates": [],
                }
            }
        ),
    )
    assert gate.line_materials[cmp_x] == cmp_m
    leak_check = harness.render_checked(
        [{"n": 1, "claim": {"kind": "defenders", "ref": f_pos_a, "square": "d5"}, "record": {"square": "d5", "piece": "p", "attackers": [], "defenders": []}}],
        codes_only=True,
        square_refs=gate.square_refs,
        ref_positions=gate.ref_positions,
        line_materials=gate.line_materials,
    )
    assert "인용코드:" not in leak_check and "f… 코드는 단독 인용 불가" in leak_check
    gate.new_moment()

    j3 = f"j1.{_hex24('1')}"
    x1 = f"x1.{_hex24('2')}"
    m1 = f"m1.{_hex24('3')}"
    b3 = f"b3.{_hex24('4')}"
    f1 = f"f1.{_hex24('5')}"
    j6 = f"j2.{_hex24('6')}"
    s6 = f"s1.{_hex24('7')}"
    k6 = f"k1.{_hex24('8')}"

    monkeypatch.setattr(
        frames,
        "check",
        lambda args, records, version=None: {
            "held": [],
            "uncheckable": [],
            "ambiguous": [],
            "search_numbers": 0,
            "version": version,
        },
    )

    fen = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"
    records = {
        x1: (
            "explored_line",
            {
                "start": {"fen": fen},
                "plies": [],
                "ledger": {
                    "ref": m1,
                    "plies": [],
                    "net": {"white": 0, "black": 0},
                    "standing": {
                        "start": {"white_minus_black": 0},
                        "end": {"white_minus_black": 0, "leader_at_end": "level"},
                    },
                    "captured": {"by_white": [], "by_black": []},
                },
            },
        ),
        b3: (
            "board_item",
            {
                "square": "d5",
                "piece": "black pawn on d5",
                "entry": {
                    "square": "d5",
                    "piece": "black pawn on d5",
                    "attackers": [{"piece": "Pe4"}],
                    "defenders": [],
                },
            },
        ),
    }

    class _StubServer:
        def __init__(self):
            self.calls = []
            self.submits = []

        async def call_tool(self, name, arguments):
            self.calls.append((name, arguments))
            if name == "game_overview":
                lines = [
                    {"ply": p, "move": f"m{p}", "grade": "inaccuracy" if p == 6 else "best", "loss": 80 if p == 6 else 0}
                    for p in range(1, 11)
                ]
                lines[2] = {"ply": 3, "move": "2.exd5", "grade": "blunder", "loss": 300}
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text=json.dumps({"lines": lines}))],
                    isError=False,
                )
            if name == "ply":
                ply = arguments["ply"]
                payload = (
                    {"judgement": j3}
                    if ply == 3
                    else {"judgement": j6, "lines": {"best": {"ref": s6, "score_text": "+0.40"}}}
                )
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text=json.dumps(payload))],
                    isError=False,
                )
            if name == "squares":
                payload = {
                    "refs": {"pieces": f1},
                    "squares": [{"square": "d5", "piece": "black pawn on d5", "ref": b3}],
                }
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text=json.dumps(payload))],
                    isError=False,
                )
            if name == "explore":
                payload = {"ref": x1, "ledger": {"ref": m1}}
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text=json.dumps(payload))],
                    isError=False,
                )
            if name == "detail":
                kind, item = records.get(arguments["ref"], (None, None))
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text=json.dumps({"kind": kind, "item": item}))],
                    isError=kind is None,
                )
            if name == "submit_commentary":
                self.submits.append(arguments)
                if "items" in arguments:
                    resp = {"items": [{"index": i, "outcome": "accepted"} for i in range(len(arguments["items"]))]}
                else:
                    resp = {"accepted": True}
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text=json.dumps(resp))],
                    isError=False,
                )
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="{}")], isError=False)

    claims_json = json.dumps(
        {
            "claims": [
                {"kind": "line_net", "ref": "x1", "side": "white", "value": 0},
                {"kind": "defenders", "ref": "b3", "square": "d5", "value": []},
            ]
        }
    )
    pass_judge = _reply(json.dumps({"pass": True, "problems": []}))
    agent = _Model(
        [
            _reply(calls=[("squares", {"game": "g", "ply": 3, "squares": ["d5"]}), ("explore", {"game": "g", "ply": 3, "moves": ["exd5"]})]),
            _reply(f"FACTS\n```json\n{claims_json}\n```"),
            _reply(calls=[("detail", {"game": "g", "ref": "x1"})]),
            _reply(
                calls=[
                    (
                        "submit_commentary",
                        {
                            "ply": 3,
                            "sentences": [
                                {"text": "d5 칸 수비가 없다.", "class": "sourced", "cites": ["b3", "m1", f1]}
                            ],
                        },
                    )
                ]
            ),
            _reply("done"),
            _reply(
                calls=[
                    (
                        "submit_commentary",
                        {
                            "items": [
                                {
                                    "ply": 6,
                                    "sentences": [
                                        {
                                            "text": "6수 부정확.",
                                            "class": "sourced",
                                            "cites": ["s1", k6],
                                        }
                                    ],
                                }
                            ]
                        },
                    )
                ]
            ),
        ]
    )
    spec = rx_run.RunSpec(
        arm="H",
        set_name="validation",
        game="g",
        pgn=GAME,
        moments=[3],
        base=tmp_path,
        records=tmp_path,
        work=tmp_path,
        game_id="g",
        harness_revision=20,
    )
    log = rx_run.AgentLog(tmp_path / "RUN20" / "agent.jsonl", "RUN20")
    server = _StubServer()
    messages = [{"role": "system", "content": "SYSTEM"}, {"role": "user", "content": "TASK"}]
    totals = {"turns": 0, "tool_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}
    reason = anyio.run(
        harness.harness_loop,
        server,
        agent,
        messages,
        [
            {"type": "function", "function": {"name": n, "parameters": {"properties": {}}}}
            for n in ("ply", "squares", "explore", "detail", "submit_commentary")
        ],
        spec,
        log,
        totals,
        rx_run._loop,
        _Model([pass_judge]),
        [(3, "2.exd5")],
    )
    log.close()
    assert reason == "done"

    # Writer sees short `[물질 코드: m1]` / `[인용코드: b3]` and minimal submit schema.
    writer_msg = agent.requests[2][-1]["content"]
    assert "물질 코드: m1" in writer_msg and "인용코드: b3" in writer_msg
    t2_submit_schema = next(f for f in agent.tools[2] if f["name"] == "submit_commentary")["parameters"]
    assert set(t2_submit_schema["properties"]) == {"ply", "sentences"}

    # Short ref `detail("x1")` resolved before reaching server.
    assert any(name == "detail" and args["ref"] == x1 for name, args in server.calls)

    # Tier 2 submit auto-filled `game`, `agent`, `j3`, resolved `b3`/`m1`, dropped `f1`.
    assert len(server.submits) == 2
    t2_sub = server.submits[0]
    assert t2_sub["game"] == "g" and t2_sub["agent"] == {"name": "commentator"}
    assert set(t2_sub["sentences"][0]["cites"]) == {b3, m1, j3}

    # Tier 1 submit received minimal schema and resolved `s1`, injected `j6`, dropped `k6`.
    t1_submit_schema = next(f for f in agent.tools[5] if f["name"] == "submit_commentary")["parameters"]
    assert set(t1_submit_schema["properties"]) == {"items"}
    t1_sub = server.submits[1]
    assert t1_sub["game"] == "g" and t1_sub["agent"] == {"name": "commentator"}
    assert set(t1_sub["items"][0]["sentences"][0]["cites"]) == {s6, j6}
