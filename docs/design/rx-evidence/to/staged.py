"""Harness pilot (not a reviewed packet): arm A (guide v8, Haiku, cached) plus
  --info    each fixed moment's three lines played out by Calliope (lines-<set>.json) in the task
  --staged  per fixed moment: facts -> the decisive cause -> a judge (same model, A2 rules, no key
            causes) -> pass: submit / fail: back to facts with the judge's reasons (2 retries at most)
Records go to ~/.local/share/calliope/rx/trial/runs.

python staged.py --game NAME [--info] [--staged] [--runs N] [--model M]
"""

import argparse
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import anyio

REPO = Path("/mnt/d/00_프로젝트/Calliope")
sys.path.insert(0, str(REPO))

from tools.rx import run as rx  # noqa: E402
from tools.rx.manifest import MANIFEST, RX_DATA, verify  # noqa: E402
from tools.rx.model import DEFAULT_MODEL, OpenRouter, read_env_file  # noqa: E402

HERE = Path(__file__).resolve().parent
PGNS = RX_DATA / "sets"
RECORDS = RX_DATA / "trial" / "runs"
RETRIES = 2
TOKENS = 6_000_000

STAGED_TASK = (
    "이 대국은 Calliope에 이미 열려 있어. 게임 id는 {game_id}야. open_game을 다시 부르지 마. "
    "고정 장면 {moments}을 한 장면씩 해설할 거야. 장면마다 내가 단계를 알려 줄게. 단계 지시를 따르고, "
    "제출하라는 지시가 있기 전에는 submit_commentary를 부르지 마."
)
STAGE_FACTS = (
    "[{name} — 1단계: 사실] 이 장면에서 확인되는 사실을 도구로 모아서 목록으로 써. 각 사실에 근거(ref)를 붙이고, "
    "수순을 둬 본 결과(기물 변화, 평가)도 사실로 쓸 수 있어. 아직 해설이나 제출은 하지 마."
)
STAGE_CAUSE = (
    "[{name} — 2단계: 결정적 원인] 위 사실로 이 수가 그 판정을 받은 결정적 원인 하나를 사슬로 써: "
    "그 수 → 상대의 구체적 응수나 수순 → 결과(기물 몇 점을 얻거나 잃음, 체크메이트, 또는 아무것도 얻지 못함). "
    "보조 원인은 최대 둘. 아직 제출하지 마."
)
STAGE_RETRY = (
    "[{name} — 판정: 통과하지 못함] 이유: {problems}\n필요하면 도구(explore, facts, judge_move 등)로 사실을 더 확인하고, "
    "1단계(사실)부터 다시 해. 목록을 다시 쓰고 나면 결정적 원인을 다시 쓰라고 할게."
)
STAGE_SUBMIT = (
    "[{name} — 3단계: 제출] 판정을 {how}. 이 장면의 해설을 submit_commentary로 제출해. 결정적 원인을 먼저 쓰고, "
    "가이드의 형식을 따라. 거부되면 고쳐서 다시 제출해."
)
NOT_YET = "아직 제출 단계가 아니야. 지금 단계의 지시를 따라 글로 답해 줘."

JUDGE_SYSTEM = """너는 체스 해설의 검수자야. 해설자가 한 장면에 대해 모은 사실 목록과, 그것으로 쓴 결정적 원인을 받는다.

먼저 알아 둘 것:
- 수가 나쁜 이유는 보통 엔진 라인(상대의 최선 응수와 그 뒤 수순)이 보여 주는 결과다. 그 수순이 실제 대국에서 두어지지 않았어도 정당한 원인이다.
- 평가 수치의 차이를 물질 점수로 정확히 맞춰 설명할 필요는 없다. 기물 득실, 체크메이트, 또는 "아무것도 얻지 못함" 같은 결과가 있으면 충분하다.

다음 중 하나라도 해당할 때만 실패로 판정해:
1. 근거 없음: 결정적 원인이 사실 목록에 없는 수순, 기물 득실, 평가를 주장한다.
2. 사실에서 멈춤: "공격받는다", "공격이 계속된다", "평가가 떨어졌다"에서 끝나고 결과(무엇을 잃거나 얻는지)가 없다.
3. 확인 안 된 득실: 기물을 따거나 잃는다고 하는데 그 수순을 둬 본 결과가 사실 목록에 없다. 또는 지켜지는 기물을 잡을 수 있다고 한다.
4. 비교 없음: 엔진 최선 수를 뒀다면 무엇이 달랐는지 전혀 말하지 않는다.
이 넷에 해당하지 않으면 통과로 판정해. 더 나은 표현이 가능하다는 이유로 실패시키지 마.
정답이나 특정 수순을 알려 주지 마. 실패 이유는 최대 세 개, 각각 한 문장으로.
JSON 하나로만 답해: {"pass": true 또는 false, "problems": ["..."]}"""


def info_block(set_name: str, game: str, plies: list[int], names: list[str]) -> str:
    data = json.loads((HERE / f"lines-{set_name}.json").read_text(encoding="utf-8"))
    out = ["\n\n아래는 각 고정 장면에서 Calliope가 직접 둬 본 수순이야. 기물은 백 기준이고 그 장면(수를 두기 전)을 0으로 셌어. "
           "평가는 수순 끝에서 엔진이 본 값(백 기준)이야."]
    labels = {"best": "엔진 최선 수순", "played": "둔 수 뒤 엔진 라인", "game": "실제 대국에서 이어진 수순"}
    for ply, name in zip(plies, names):
        rec = data[f"{game}-{ply}"]
        out.append(f"\n{name} (ply {ply})")
        for key in ("best", "played", "game"):
            if key not in rec:
                continue
            r = rec[key]
            mats = [p["material"] for p in r["plies"]]
            if r.get("game_over"):
                end = "수순 끝에서 대국 종료(체크메이트 등)"
            elif r.get("end_score") and r["end_score"].get("mate") is not None:
                end = f"끝 평가 메이트 {r['end_score']['mate']:+d}"
            elif r.get("end_score"):
                end = f"끝 평가 {r['end_score']['cp'] / 100:+.2f}"
            else:
                end = "끝 평가 없음"
            out.append(f"- {labels[key]}: {' '.join(r['moves'])} | 수마다 기물 {mats} | {end}")
    return "\n".join(out)


class GatedSession:
    """The MCP session with submit_commentary held back until the submit step."""

    def __init__(self, session):
        self.session = session
        self.open = False
        self.blocked = 0

    async def call_tool(self, name, arguments):
        if name == "submit_commentary" and not self.open:
            self.blocked += 1
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=NOT_YET)], isError=True)
        return await self.session.call_tool(name, arguments)

    def __getattr__(self, item):
        return getattr(self.session, item)


def _parse(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    for candidate in (match.group(0), match.group(0).replace('\\"', '"')):
        try:
            verdict = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(verdict, dict) and isinstance(verdict.get("pass"), bool):
            return verdict
    return {}


def judge(model: OpenRouter, header: str, facts: str, cause: str) -> tuple[dict, dict]:
    messages = [{"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": f"{header}\n\n## 사실 목록\n{facts}\n\n## 결정적 원인\n{cause}"}]
    usage = {"cost": 0.0, "input_tokens": 0}
    text = ""
    for _ in range(2):  # one more ask when the answer is not the JSON asked for
        reply = model.complete(messages, [])
        usage["cost"] += reply.usage.get("cost") or 0.0
        usage["input_tokens"] += reply.usage.get("input_tokens") or 0
        text = reply.message.get("content") or ""
        verdict = _parse(text)
        if verdict:
            verdict["problems"] = [str(p) for p in (verdict.get("problems") or [])][:3]
            return verdict, usage
    return {"pass": False, "problems": ["판정을 읽지 못함"], "raw": text[:500], "unreadable": True}, usage


def last_text(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "assistant" and m.get("content"):
            return m["content"]
    return ""


def make_staged_loop(entry_plies, names, headers, judge_model):
    plain_loop = rx._loop

    async def staged_loop(session, model, messages, tools, spec, log, totals, retries, sent):
        gated = GatedSession(session)
        log.write({"type": "harness", "stage": "start", "moments": names})
        for ply, name in zip(entry_plies, names):
            attempt = 0
            how = "통과했어"
            while True:
                gated.open = False
                messages.append({"role": "user", "content": STAGE_FACTS.format(name=name)})
                log.write({"type": "harness", "stage": "facts", "ply": ply, "attempt": attempt})
                reason = await plain_loop(gated, model, messages, tools, spec, log, totals, retries,
                                          len(messages) - 1)
                if reason != "done":
                    return reason
                facts = last_text(messages)
                messages.append({"role": "user", "content": STAGE_CAUSE.format(name=name)})
                log.write({"type": "harness", "stage": "cause", "ply": ply, "attempt": attempt})
                reason = await plain_loop(gated, model, messages, tools, spec, log, totals, retries,
                                          len(messages) - 1)
                if reason != "done":
                    return reason
                cause = last_text(messages)
                verdict, usage = await anyio.to_thread.run_sync(judge, judge_model, headers[ply], facts, cause)
                totals["cost"] += usage.get("cost") or 0.0
                totals["judge_input_tokens"] = totals.get("judge_input_tokens", 0) + (usage.get("input_tokens") or 0)
                log.write({"type": "judge", "ply": ply, "attempt": attempt, "verdict": verdict, "usage": usage,
                           "facts": facts, "cause": cause})
                if verdict["pass"] or verdict.get("unreadable"):  # an unreadable verdict never blocks
                    break
                if attempt >= RETRIES:
                    how = f"{RETRIES + 1}번 통과하지 못했지만 시도 한도에 닿았어"
                    break
                attempt += 1
                problems = "; ".join(str(p) for p in verdict.get("problems") or [])
                messages.append({"role": "user", "content": STAGE_RETRY.format(name=name, problems=problems)})
            gated.open = True
            messages.append({"role": "user", "content": STAGE_SUBMIT.format(name=name, how=how)})
            log.write({"type": "harness", "stage": "submit", "ply": ply, "attempts": attempt + 1})
            reason = await plain_loop(gated, model, messages, tools, spec, log, totals, retries,
                                      len(messages) - 1)
            if reason != "done":
                return reason
        log.write({"type": "harness", "stage": "end", "blocked_submissions": gated.blocked})
        return "done"

    return staged_loop


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--game", required=True)
    p.add_argument("--set", default="validation")
    p.add_argument("--info", action="store_true")
    p.add_argument("--staged", action="store_true")
    p.add_argument("--runs", type=int, default=1)
    a = p.parse_args()

    read_env_file(REPO / ".env")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entry = next(e for e in manifest["sets"][a.set] if e["name"] == a.game)
    pgn = verify(a.set, entry, PGNS)
    tag = {"trial": True, "harness_pilot": True, "info": a.info, "staged": a.staged, "cache": True}
    rx.lessons = lambda spec: ("", {"lesson_set": None, "lesson_ids": [], "trial": tag})

    plies = sorted(entry["moments"])
    names = rx.numbered(pgn, plies)
    extra = info_block(a.set, a.game, plies, names) if a.info else ""
    if a.staged:
        rx.TASK_BY_ID = STAGED_TASK.replace("{moments}", ", ".join(names))
        headers = {}
        for ply, name in zip(plies, names):
            ref = json.loads((REPO / "tools/rx/references_v1" / a.set / f"{a.game}-{ply}.json").read_text(encoding="utf-8"))
            ev = ref["digest"]["evaluation"]
            headers[ply] = (f"장면: {name} (판정 {ref['digest'].get('grade_ko') or ref['digest'].get('grade')}, "
                            f"둔 수 평가 {ev.get('played')}, 엔진 최선 {ev.get('best_move')} {ev.get('best')})")
        rx._loop = make_staged_loop(plies, names, headers, OpenRouter(a.model, cache=False))
    rx.TASK_BY_ID = rx.TASK_BY_ID + extra.replace("{", "{{").replace("}", "}}")

    spec = rx.RunSpec(arm="A", set_name=a.set, game=a.game, pgn=pgn, moments=entry["moments"],
                      base=RX_DATA / "base" / a.set, records=RECORDS, work=RX_DATA / "work",
                      model=a.model, game_id=entry.get("game_id"), cache=True)
    spec.bounds.tokens = TOKENS  # the pilot's bound for every arm (RX2's 2M is too low for the stages)
    RECORDS.mkdir(parents=True, exist_ok=True)
    for _ in range(a.runs):
        result = anyio.run(rx.run_once, spec)
        print(json.dumps({"model": a.model, "game": a.game} | tag | result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
