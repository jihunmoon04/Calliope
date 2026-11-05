"""Lesson sets (RX4-D §2.2, §2.4): the file that keeps a set, its checks, and its rendering into the
system prompt.

A set's file (`tools/rx/lessons/<id>.json`) keeps every lesson whole, with its `id`, `versions` and
`source` (the Train runs and plies it answers), and the set's `status` and checks. Only the strategy
reaches the agent (review N5): `render` writes each lesson's `condition`, `action`, `success` and
`fallback`, and nothing else.

What a run may carry depends on the set's status (RX4a review B1, `use_problems`):

| status | written by | runs it may serve |
| --- | --- | --- |
| `CANDIDATES` | the evaluator (§2.3 step 1) | screening only: Train, one `candidate_id` |
| `CHECKING` | the kept candidates (§2.3 step 3) | the set check: Train, the whole set |
| `APPROVED` | the owner's approval (§2.3 step 4) | Train and Validation, the whole set |
| `PROMOTED` | the Validation result (§5) | Train and Validation, the whole set |
| `NOT_PROMOTED` | the Validation result (§5) | none, except to reproduce its result (`--reproduce`) |

`APPROVED` and later need the owner's `approval` (`by`, `date`). Every set names the `versions` it was
written for (`guide`, `build_id`); a run on another guide or build is refused, and the set must be written
and approved again (review N2).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

LESSONS = Path(__file__).resolve().parent / "lessons"
RENDERED_FIELDS = ("condition", "action", "success", "fallback")
MAX_LESSONS = 8
MAX_CHARS = 400  # a lesson's rendered text, in Korean (§2.2)
HEADING = (
    "## 상황별 전략\n"
    "아래는 특정 상황에서 쓰는 전략이야. 각 항목의 상황이 지금 장면에 맞을 때만 따라 줘. "
    "사실은 언제나 Calliope 도구의 결과에서 가져와 줘."
)
# §2.2: an action is a call to one of these, with what to pass (RX4a re-review C1)
ACTION_TOOLS = ("explore", "facts", "judge_move", "detail")
_TOOL = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(ACTION_TOOLS) + r")(?![A-Za-z0-9_])")
_CALL = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)\s*\(")  # `name(`: a call by name
MIN_ARGUMENT_CHARS = 6  # beyond the tool's name: what to pass, where
# a square or a numbered move names a game, never a strategy (§2.2)
_SQUARE = re.compile(r"(?<![A-Za-z0-9_])[a-h][1-8](?![A-Za-z0-9_])")
_NUMBERED = re.compile(r"(?<![0-9])[0-9]{1,3}\.(?:\.\.)?\s*[KQRBNO]?[a-h]?x?[a-h][1-8]")


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _lesson_text(lesson: dict) -> str:
    action = lesson.get("action") or []
    if isinstance(action, str):
        action = [action]
    return "\n".join(
        [
            f"- 상황: {lesson['condition']}",
            "  할 일: " + "; ".join(str(x) for x in action),
            f"  확인: {lesson['success']}",
            f"  안 될 때: {lesson['fallback']}",
        ]
    )


def problems(doc: dict) -> list[str]:
    """What keeps a set from running: a missing field, a lesson too long, a square or numbered move
    in a lesson, more than eight lessons in a set that is not a candidates file, a repeated id."""

    out = []
    lessons = doc.get("lessons") or []
    if not lessons:
        out.append("no lessons")
    if doc.get("status") != "CANDIDATES" and len(lessons) > MAX_LESSONS:
        out.append(f"{len(lessons)} lessons, at most {MAX_LESSONS}")
    ids = [x.get("id") for x in lessons]
    if len(set(ids)) != len(ids) or None in ids:
        out.append("lesson ids missing or repeated")
    for lesson in lessons:
        name = lesson.get("id", "?")
        missing = [f for f in RENDERED_FIELDS if not lesson.get(f)]
        if missing:
            out.append(f"{name}: missing {', '.join(missing)}")
            continue
        out += [f"{name}: {p}" for p in action_problems(lesson["action"])]
        out += [f"{name}: {p}" for p in version_problems(lesson, doc)]
        text = _lesson_text(lesson)
        if len(text) > MAX_CHARS:
            out.append(f"{name}: {len(text)} characters, at most {MAX_CHARS}")
        if _SQUARE.search(text) or _NUMBERED.search(text):
            out.append(f"{name}: names a square or a move")
    return out


def action_problems(action) -> list[str]:
    """C1: the action is a list of steps, none empty; at least one names a tool of `ACTION_TOOLS`
    with what to pass; a step that calls something by name (`name(`) calls one of them."""

    steps = [action] if isinstance(action, str) else action
    if not isinstance(steps, list) or not steps:
        return ["action is not a list of steps"]
    out = []
    if any(not isinstance(s, str) or not s.strip() for s in steps):
        out.append("an action step is empty")
    texts = [s for s in steps if isinstance(s, str)]
    for s in texts:
        for called in _CALL.findall(s):
            if called not in ACTION_TOOLS:
                out.append(f"action calls {called!r}, not one of {', '.join(ACTION_TOOLS)}")
    concrete = [s for s in texts if _TOOL.search(s)
                and len(_TOOL.sub("", s).strip(" .;:,()")) >= MIN_ARGUMENT_CHARS]  # fmt: skip
    if not concrete:
        out.append(f"no action step uses {', '.join(ACTION_TOOLS)} with what to pass")
    return out


def version_problems(lesson: dict, doc: dict) -> list[str]:
    """N3: a lesson's own versions are the set's. The set fixes them when it is written, and the owner
    approves them with it; a lesson naming a version the set does not fix, or another value, is
    refused."""

    mine = lesson.get("versions") or {}
    fixed = doc.get("versions") or {}
    out = []
    for key, value in sorted(mine.items()):
        if key not in fixed:
            out.append(f"versions.{key} is not fixed by the set")
        elif fixed[key] != value:
            out.append(f"versions.{key} {value!r} is not the set's {fixed[key]!r}")
    return out


STATUSES = ("CANDIDATES", "CHECKING", "APPROVED", "PROMOTED", "NOT_PROMOTED")
APPROVED = ("APPROVED", "PROMOTED", "NOT_PROMOTED")


def use_problems(doc: dict, *, set_name: str, candidate: str | None, guide: str,
                 build_id: str | None, reproduce: bool = False) -> list[str]:  # fmt: skip
    """Why this set may not serve this run (review B1, N2): its status against the run's purpose,
    the approval, the versions it was written for. A `NOT_PROMOTED` set is kept and not used
    (RX4-D §5): it runs only to reproduce its result, asked for by name (re-review N4)."""

    status = doc.get("status")
    out = []
    if status not in STATUSES:
        return [f"status {status!r} is not one of {', '.join(STATUSES)}"]
    if status == "CANDIDATES":
        if candidate is None:
            out.append("a CANDIDATES file serves screening only: name one --candidate")
        if set_name != "train":
            out.append("candidates are screened on Train only")
    else:
        if candidate is not None:
            out.append(f"a {status} set runs whole: no --candidate")
        if status == "CHECKING" and set_name != "train":
            out.append("a set not approved by the owner runs on Train only")
        if status == "NOT_PROMOTED" and not reproduce:
            out.append("a NOT_PROMOTED set is not used: it runs only with --reproduce")
        if status in APPROVED:
            approval = doc.get("approval") or {}
            if not (approval.get("by") and approval.get("date")):
                out.append(f"a {status} set needs the owner's approval (by, date)")
    versions = doc.get("versions") or {}
    if versions.get("guide") != guide:
        out.append(f"written for guide {versions.get('guide')!r}, the run uses {guide!r}: write and "
                   "approve the set again")  # fmt: skip
    if build_id is None or versions.get("build_id") != build_id:
        out.append(f"written for build {versions.get('build_id')!r}, the base is {build_id!r}: write "
                   "and approve the set again")  # fmt: skip
    return out


def select(doc: dict, candidate: str | None) -> list[dict]:
    """The lessons a run carries: the whole set, or one candidate alone (§2.3 step 2)."""

    lessons = doc.get("lessons") or []
    if candidate is None:
        chosen = lessons
    else:
        chosen = [x for x in lessons if x.get("id") == candidate]
        if not chosen:
            raise ValueError(f"no lesson {candidate!r} in {doc.get('id')}")
    if len(chosen) > MAX_LESSONS:  # whatever the file holds, a run carries at most eight (B1)
        raise ValueError(f"{len(chosen)} lessons in one run, at most {MAX_LESSONS}")
    return chosen


def render(lessons: list[dict]) -> str:
    """The prompt's text of the lessons: the four strategy fields only; '' for no lessons."""

    if not lessons:
        return ""
    return HEADING + "\n\n" + "\n\n".join(_lesson_text(x) for x in lessons)


def digest(text: str) -> str:
    """`lesson_set_digest` (review N4): the sha256 of the rendered text; B's is the digest of ''."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
