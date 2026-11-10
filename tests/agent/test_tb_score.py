"""TB-D P2: the score command — `judge_v2r`'s answer read strictly, a cut or unreadable answer asked
once more, a moment without commentary counted as a failure, the row's judging fields."""

from __future__ import annotations

import json

from tools.rx import model as rx_model
from tools.rx import score as rx_score

GOOD = {"sentences": [{"n": 1, "verdict": "ok"},
                      {"n": 2, "verdict": "wrong", "kind": "grade", "why": "x"}],
        "causes": [{"cause": 1, "verdict": "explained"}], "score": 4}  # fmt: skip


def test_a_verdict_must_judge_every_sentence_and_cause():
    assert rx_score.parse_verdict("note " + json.dumps(GOOD) + " end", 2, 1)["score"] == 4
    assert rx_score.parse_verdict(json.dumps(GOOD), 3, 1) is None  # a sentence left out
    assert rx_score.parse_verdict(json.dumps(GOOD), 2, 2) is None  # a cause left out
    bad = dict(GOOD, score=9)
    assert rx_score.parse_verdict(json.dumps(bad), 2, 1) is None
    odd = dict(GOOD, sentences=[{"n": 1, "verdict": "fine"}, {"n": 2, "verdict": "ok"}])
    assert rx_score.parse_verdict(json.dumps(odd), 2, 1) is None
    assert rx_score.parse_verdict("no json", 2, 1) is None


class _Judge:
    def __init__(self, replies):
        self.replies = list(replies)

    def complete(self, messages, tools):
        return self.replies.pop(0)


def _reply(text, stop="end_turn"):
    return rx_model.Reply(message={"content": text},
                          usage={"cost": 0.01, "input_tokens": 100, "output_tokens": 10},
                          body_fields=[], stop=stop)  # fmt: skip


CONTENT = {"sentences": [{"n": 1}, {"n": 2}], "key_causes": [{"cause": 1}]}


def test_a_cut_or_unreadable_answer_is_asked_once_more():
    verdict, usage = rx_score.judge_moment(
        _Judge([_reply('{"sentences": [', "max_tokens"), _reply(json.dumps(GOOD))]), "s", CONTENT
    )
    assert verdict["score"] == 4 and usage["asked"] == 2
    verdict, usage = rx_score.judge_moment(_Judge([_reply("?"), _reply("??")]), "s", CONTENT)
    assert verdict is None and usage["asked"] == 2


def test_a_moment_without_commentary_is_a_failure_in_the_rates():
    from tools.rx.report import moment_values

    judged = moment_values(GOOD, ["decisive"])
    missing = moment_values(None, ["decisive"])
    out = rx_score.rates([judged, missing])
    assert out["M2b"] == 0.5  # the missing moment's decisive cause is not explained
    assert out["M1b"] == 50.0 and out["sentences"] == 2
    assert out["score"] == 4.0


def test_the_score_judge_is_its_own_prompt_and_fixed_model():
    assert rx_score.PROMPT.name == "judge_v2r.md" and rx_score.PROMPT.exists()
    assert rx_score.JUDGE_MODEL == "claude-sonnet-5-5"
    assert len(rx_score.schema_digest()) == 16
    assert rx_score.GAMES == ("184800218248", "185264271324")
