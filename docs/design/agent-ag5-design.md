# Agent — AG5-D design: guidance an agent reaches by itself

Status: **rev. 2 — independent review of rev. 1 (`69e7d1b`) NOT_READY (B1, B2; N1, N2) applied
(§12); re-review of rev. 2 (`54a24ac`) READY_FOR_MERGE, notes N3 and N4 applied (§13)**. Date: 2026-10-16. Base: `main @ dfbf8d7` (AG4-D AM1 merged). The trial's host faults are
fixed in HIMARI first (its PRs #44, #45, merged), so a repeat measures Calliope's guidance. Inputs:
[`agent-mcp-design.md`](agent-mcp-design.md) (AG-D: §2 the shape, §3 tools, §4 propositions, §6 the
prompts, §7 resources and registries, §10 build identity); MCP 2025-11-25 (server features: tools
are model-controlled, resources application-driven, prompts user-controlled; `instructions` a hint
the client may use; resource annotations); a live trial in HIMARI v3 (2026-10-16, §0).

Calliope tells an agent how to reason and how to check itself in two MCP prompts (AG-D §6). A
prompt is chosen by the **user**: the specification calls prompts user-controlled, and a host does
not let the model open them. The server's `instructions` end by sending the agent there: "자세한
방법은 프롬프트 calliope_commentary와 calliope_check, 용어는 calliope://glossary/ko에 있습니다". An agent
that was not handed the prompt by its user has no way to the method, and goes looking for it.

## 0. The trial (2026-10-16)

HIMARI v3 (`main @ b5da0ea`: server instructions in the system message, resources as the model's
`list_resources` / `read_resource` tools, prompts in the user's composer) with Calliope `main @
dfbf8d7` over stdio in HIMARI's server sandbox, one shared process. Model `openai/gpt-6-luna`. One
user message: open `1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. d3 h6 *`, analyse ply 10 (5...h6),
write and save its commentary. HIMARI stops a turn after 16 model requests (Runs).

Calls by Run (24 calls in 16 Runs):

| Runs | Calls |
| --- | --- |
| 1–2 | `open_game` (plies 10), `ply` 10 — as intended |
| 2–10 | looking for the method: `definitions` 8 times (queries `"calliope_commentary calliope_check"`, `"proposition move grade …"`, `"proposition.move"`; kinds `proposition`, `agent_definition`, `agent_definition_v1`; id `agent.himari`); `list_resources` twice (refused by HIMARI: a `cursor` fault, fixed there); `read_resource` of `calliope://prompts/calliope_commentary` and `calliope://prompts/calliope_check` (guessed, refused: not listed) and of `calliope://definitions` (a 32,000-character page) |
| 11–15 | `submit_commentary` twice, each followed by `commentary` (empty); a second `calliope://definitions` page |
| 16 | `read_resource` of three more guessed URIs (`calliope://prompts/commentary`, `calliope://prompt/calliope_commentary`, `calliope://agent_definitions`); `definitions` by ids |

No `judge_move`, `facts` or `explore`: the agent wrote from `ply` alone. Both submissions came back
"outcome unknown" because of a HIMARI fault (nested tool arguments were not encoded; fixed in
HIMARI, PR #45); Calliope answers the same submission with `accepted: false` and its violations.
They would have been refused: the agent wrote the registry's ids as proposition kinds
(`proposition.judgement`, `proposition.engine_line` for `judgement`, `engine_line`), the format the
commentary guide shows and the agent never read.

The turn ended at the limit: 16 Runs, 89 s, 425,673 input tokens (2,318 on the first Run, 39,177 on
the last; 2,125 cached on each from the second) and 3,881 output tokens, no commentary.
Two of the method searches failed on the `definitions` tool itself: a query of several words is
matched as one substring, and an unknown kind (`agent_definition`) answers an empty list without
saying which kinds there are (26).

The failure is in how Calliope points to its method, not in its facts or tools: the agent found
the tools, then spent its turn looking for what the instructions promised, and submitted without it.

## 1. Decisions

| # | Decision |
| --- | --- |
| G1 | **Each MCP feature in its role.** The `instructions` give the minimal working order and the exact URIs of the method; **resources** hold the method in full, for the agent to read when it writes; **prompts** stay, the same method for a user who picks it; **tools** do the work, and their descriptions carry what an agent needs at the call (G6). No agent loop in Calliope: the host's agent plans, Calliope serves facts, judgements, checks and the method. |
| G2 | **The method as two resources**, `calliope://guides/commentary_ko` and `calliope://guides/check_ko` (§4), rendered from the same files as the prompts (`agent/prompts/commentary_ko_v1.md`, `check_ko_v1.md`): one source, so a resource and its prompt never differ but for the target. The prompt files, their digests, the prompt ids and the registries are unchanged. |
| G3 | **New `instructions`** (§3): what Calliope is, the order of one commentary in four steps, the proposition kinds as they are submitted, the two guide URIs and that the agent reads them before writing, that the prompts are the same method for the user, and the rules that must hold even if the guides are not read. |
| G4 | **`definitions` finds what an agent asks for** (§5): a query of several words matches the entries that contain every word; an unknown kind answers with the kinds there are. |
| G5 | **What a host must do is stated** (§2): Calliope's full guidance needs a host that gives its model the server's instructions and lets it read resources. Where a host does neither, the tool descriptions (G6) still carry the working order's essentials; no more is guaranteed. |
| G6 | **Tool descriptions carry the essentials** (§5.2), the one channel every host gives its model with each tool: `ply` says it is where a ply starts and names the method's URI; `submit_commentary` gives the proposition kinds as submitted, says that `proposition.<kind>` is the id of a kind's definition (its fields, by `definitions`) and never a kind, and names both guides; `definitions` names its kinds (§5). |
| G7 | **A refusal says how to write a kind** (§5.3): a proposition whose kind is `proposition.<kind>` for a kind there is is refused as today, and its violation says to write `<kind>`. |
| G8 | **The guidance is part of the agent build** (§6): `agent_build()` gains `guidance`, the version `agent_guidance_v1` of the instructions, the tool descriptions and the `definitions` search, so a stored commentary says under which guidance it was written. Bumped with any change to them; a test pins it to their digest. Neither the reasoning build nor any cache key changes. |
| G9 | **Not changed:** the prompts (names, arguments, text), the registries and their digests, tool names and arguments (`TOOLS_VERSION` stays `agent_tools_v3`, as AG4), tool answers but for §5's `kinds` field, what a submission must satisfy (G7 changes a message only), the viewer. Not added: a tool that serves the method; method links in tool answers (§7). |

## 2. Hosts: what Calliope can count on

MCP leaves it to the host whether its model sees the server's `instructions` (the specification
calls them a hint a client may use, for example in its system prompt) and whether its model can
read resources (resources are application-driven: a host may give them to its model, let the user
attach them, or neither). Tool descriptions are the one thing every host gives its model, with the
tools. So the guidance reaches an agent in layers:

| The host's model sees | What reaches the agent | Supported |
| --- | --- | --- |
| the instructions, and can read resources | the working order, the kinds, the rules; the full method and the checklist when it reads them | **Yes — the supported setting**, the one §8 tests |
| the instructions; no resources | the working order, the kinds, the rules; not the full method (a user may still pick the prompts) | Limited: commentary may be refused more often |
| no instructions; resources it can read | what the tool descriptions say (G6), the guides once the agent reads them — found through `ply`'s and `submit_commentary`'s descriptions | Limited |
| neither | the tool descriptions only | Not guaranteed |

- **Calliope guarantees** the server side: the instructions in `initialize`, the guides listed and
  readable, the descriptions of §5.2, and refusals that say what to fix. It does not and cannot
  guarantee what a host shows its model.
- **HIMARI v3 is a supported host:** it puts a server's instructions in the system message (V3-P60
  §3, operator setting `system`) and gives the model `calliope/list_resources` and
  `calliope/read_resource`. The trial of §8 runs there.
- Whether a host gives the instructions to its model is the host's to test (HIMARI tests it, V3-P60);
  Calliope's tests (§9) check what Calliope sends.

## 3. The instructions

Replaces `INSTRUCTIONS` in `agent/server.py` (about 1,040 characters; HIMARI gives a server up to
4,000):

```text
Calliope는 체스 수를 엔진과 사실 근거로 판정하고, 에이전트가 쓴 해설을 그 근거와 대조해 받아들이는 서버입니다.
해설은 이 서버가 준 정보로만, 한국어로 쓰세요.

한 수를 해설하는 순서:
1. open_game으로 게임을 엽니다(PGN, 또는 fen과 moves). 받은 게임 id를 계속 씁니다.
2. ply로 그 수의 등급·라벨·최선수·클레임을 읽습니다. 두지 않은 수는 judge_move로 판정합니다.
3. 쓰려는 근거를 확인합니다. ply의 클레임으로 충분하지 않은 "왜"는 facts·explore·judge_move로 비교해 답합니다: 더 나은 수가 하고 이 수가 하지 못한 것.
4. 확인한 것을 명제로 만들고 문장마다 명제를 인용해 submit_commentary로 제출합니다. 거부되면 표시된 곳을 고쳐 다시 제출합니다.
판을 사용자에게 보여 주려면 show_game을 씁니다.

명제의 kind는 judgement, claim, engine_score, engine_line처럼 접두사 없는 이름입니다. proposition.judgement 같은 id는
그 kind의 정의(필드)를 definitions(ids=[...])로 찾는 이름이고, proposition은 등록부의 분류입니다. 둘 다 kind로 쓰지 않습니다.

해설을 쓰기 전에 리소스 calliope://guides/commentary_ko(방법: 명제 형식, 수·숫자 표기)를, 제출 전에
calliope://guides/check_ko(점검 목록)를 읽으세요. 용어는 calliope://glossary/ko, 모르는 정의는
definitions로 찾습니다. 프롬프트 calliope_commentary·calliope_check는 같은 지침을 사용자가 고를 때 쓰는 것입니다.

꼭 지킬 것: SUPPORTED라도 ATTRIBUTED가 실패한 득실은 이 수의 성과가 아닙니다. specific_line은 한 라인에서만
성립하고, 패턴은 배치일 뿐입니다. 직접 탐색한 라인(by: agent)은 엔진의 라인이 아닙니다. 숫자·수·칸은
인용한 명제의 값만 씁니다.
```

- **Steps, not prose.** The four steps are AG-D §6's method in its own order (`ply` first, then
  checking by comparison where `ply`'s claims do not answer "why", then propositions and
  submission), short enough to act on without the guides.
- **The kinds, directly** (review B2): the trial's agent took the registry's ids for kinds. The
  three names (a kind, a definition's id, the registry's class) are told apart where every agent
  that sees the instructions reads them, not only in the guide.
- **The exact URIs, and when to read them.** "Read before writing" and "before submitting" tie each
  guide to its step. Naming the prompts once, as the user's way to the same method, removes the
  reason to look for them; a prohibition ("do not guess URIs") is not needed when the real ones are
  given.
- **The rules that must hold** stay (they were there): the server cannot check the wording (AG-D
  §6), and an agent that skips the guides must still not break them.

## 4. The guide resources

| URI | Name | Rendered from | Annotations |
| --- | --- | --- | --- |
| `calliope://guides/commentary_ko` | `commentary_guide` | `commentary_ko_v1.md` | `audience: ["assistant"]`, `priority: 1.0` |
| `calliope://guides/check_ko` | `check_guide` | `check_ko_v1.md` | `audience: ["assistant"]`, `priority: 0.8` |

- **MIME type** `text/markdown`. Title and description name what the guide is for ("How to reason
  about a move and write its commentary (Korean)", "How to check a commentary before submitting it
  (Korean)"), as the prompts' descriptions do.
- **Rendering.** A prompt formats its file with the user's `game` and `ply`. A resource formats the
  same file with the placeholders `<game>` and `<ply>`, so its target line reads "대상: 게임 <game>, 수
  <ply>." and every escaped brace (`{{ }}`) becomes the brace the prompt shows. The rest of the text
  is the prompt's, byte for byte.
- **Annotations.** `audience: ["assistant"]` says the guide is meant for the model; a host that
  ranks resources may use `priority`. Neither restricts anything.
- **Listed, not templated.** The guide does not depend on the game, so a fixed URI is enough; the
  agent already knows its game and ply.

## 5. Tools

### 5.1 `definitions`

| Input | Today | AG5 |
| --- | --- | --- |
| `query` of one word | entries whose id or statement contains it (case-insensitive) | unchanged |
| `query` of several words | the whole string as one substring (usually nothing) | entries whose id, statement or field names together contain **every** word (re-review N3: `"proposition move grade"` finds `proposition.judgement`, whose fields hold `move` and `grade`) |
| `kind` that no entry has | `{"definitions": [], "total": 0, "limit": 40}` | the same, plus `"kinds"`: every kind there is, sorted |

`ids` lookups, limits, ordering and every other answer are unchanged. A one-word query still looks
at the id and the statement only, as today.

### 5.2 Descriptions

| Tool | Added to its description |
| --- | --- |
| `ply` | "Start here for a ply: its grade, label, best move and claims. How to write its commentary: resource `calliope://guides/commentary_ko`." |
| `submit_commentary` | Replaces "kinds and fields: resource calliope://definitions, `proposition.*`" with: a proposition is `{"id", "kind", …fields}`; `kind` is one of `judgement`, `claim`, `engine_score`, `engine_line`, `material`, `attack`, `defence`, `exposed`, `pin`, `check`, `legal_moves`, `pattern`, `after_reply`, `explored_line`, `definition` — never `proposition.<kind>`, which is the id of the kind's definition (`definitions(ids=["proposition.<kind>"])` gives its fields); one judgement proposition cites the subject's own judgement; the method and examples: `calliope://guides/commentary_ko`, the checklist: `calliope://guides/check_ko`. |
| `definitions` | Its kinds: the common ones (`proposition`, `use`, `sentence_class`, `token_rule`, `check`, `prompt`) and that an unknown kind answers with the list; `proposition.<kind>` entries give the fields of a submitted proposition. |

The kinds in `submit_commentary`'s description are the verifier's (`propositions.KINDS`), written
from it, so they cannot drift.

### 5.3 The refusal of a prefixed kind

Today `{"kind": "proposition.judgement"}` is refused with `no proposition kind
'proposition.judgement'` and the list of kinds. With AG5 the same violation says what to write:
`no proposition kind 'proposition.judgement': write 'judgement' ('proposition.judgement' is the id
of its definition)`. Only the message changes, and only when the part after `proposition.` is a
kind; the refusal, its field and `expected` are as today.

## 6. Build identity

`agent_build()` (AG-D §10) gains one key, `"guidance": "agent_guidance_v1"`: the version of what
§3 and §5 change — the instructions, the tool descriptions and the `definitions` search. Like
`tools`, it names a version, not a digest; a test pins `agent_guidance_v1` to the digest of the
instructions and the descriptions, so a change to them fails until the version is bumped. The
search is pinned by its own tests (§9, `definitions`): a change to what it finds fails them, and is
a change of the guidance too (re-review N4). Every
accepted commentary then records under which guidance it was written (review N2). Stored
commentary keeps its build as written; nothing reads `guidance` to accept or refuse, and neither
the reasoning build nor any cache key changes. The prompts' and the glossary's digests are in the
build already.

## 7. Considered and left out

- **A tool that returns the method** (e.g. `guide`). Every host shows tools, so it would reach more
  hosts than a resource. It duplicates the resources and the prompts with a third surface; G6
  already puts the essentials in the descriptions. Reconsider if a host that cannot read resources
  needs the full method.
- **Method links in tool answers** (an MCP `resource_link` in `open_game` or `ply`). It would point
  to the guide when it is needed, but changes the answers of tools whose JSON is fixed (AG-D §3);
  `ply`'s description says the same.
- **The whole method in the instructions** (about 2,500 characters more). It would be in every
  request of every conversation, also when the agent only shows a game, and a host may cut long
  instructions. The four steps, the kinds and the rules are what an agent needs before it reads
  anything.
- **Accepting `proposition.<kind>` as `<kind>`.** It would hide a confusion the guidance should
  remove, and propositions are a closed format (AG-D §4); G7 says what to write instead.

## 8. Acceptance: the trial again (review N1)

After AG5, the trial of §0 is repeated in HIMARI v3 (a supported host, §2) with the same model, game,
ply and request, **three times**, each in a new conversation; each turn is recorded here. Measured
per turn: Runs; input tokens per Run and in total; cached input tokens where the provider reports
them; the calls in order; the guides read; each submission's result.

| Measure | Target |
| --- | --- |
| Guessed URIs read, prompts looked for | 0 |
| The method | `calliope://guides/commentary_ko` read before the first submission |
| Ply analysed | 10 (5...h6) |
| Evidence | what the commentary says is in the propositions it cites: `ply`'s claims where they answer it; `facts`, `explore` or `judge_move` where it compares or explains a cause that `ply` does not; no call made only to have made it |
| Propositions | kinds as submitted (`judgement`, not `proposition.judgement`); a refusal corrected on the next submission |
| Commentary | accepted, stored, shown by `commentary`; read by the reviewer: no fact, cause or number without a cited proposition; interpretation marked |
| Runs | within 8 in each of the three turns (an experimental target, not yet known to be reachable) |
| Cost | input tokens compared with §0 |

If the agent still searches or repeats itself, that is the host's to bound (HIMARI's run limit and
loop control are HIMARI's design work), and recorded here as found.

## 9. Tests (Calliope)

- **Instructions:** `initialize` carries the text of §3; it names `calliope://guides/commentary_ko`,
  `calliope://guides/check_ko`, `calliope://glossary/ko`, the tools `open_game`, `ply`,
  `judge_move`, `facts`, `explore`, `submit_commentary` and the kinds `judgement`, `claim`,
  `engine_score`, `engine_line`; every URI it names is listed by `resources/list`. These check what
  Calliope sends, not what a host shows (§2).
- **Resources:** `resources/list` lists both guides with their MIME type and annotations;
  `resources/read` of each returns the prompt's text with the target `<game>` / `<ply>` — the same
  as `prompts/get` with `game="<game>"`, `ply="<ply>"`, character for character; no `{` or `}` is
  left doubled.
- **Descriptions:** `tools/list` gives `ply`, `submit_commentary` and `definitions` the text of
  §5.2; `submit_commentary`'s kinds equal `propositions.KINDS`.
- **Refusal:** a proposition of kind `proposition.judgement` is refused with the message of §5.3; a
  kind `foo` and `proposition.foo` keep today's message.
- **`definitions`:** a two-word query finds the entry that holds both words and not the ones that
  hold one; `"proposition move grade"` finds `proposition.judgement` (by its fields); a one-word query answers as today; an unknown kind answers `kinds` (all 26 today,
  sorted) and an empty list; a known kind has no `kinds` field.
- **Build:** `agent_build()` has `guidance: agent_guidance_v1` and its other keys unchanged; the pin
  test fails when the instructions or a description change without a new version.
- **Host integration** is §8's trial, in HIMARI; HIMARI's own tests check that a server's
  instructions reach the model's system message (V3-P60).

## 10. Packet

One implementation packet, **AG5**: `agent/server.py` (instructions, the two resources, the
descriptions), `agent/build.py` (the guide rendering beside `text`, `guidance` in the build),
`agent/definitions.py` (`GUIDANCE_VERSION`), `agent/propositions.py` (§5.3's message),
`find_definitions` (§5.1), the tests of §9, the trial of §8 with its numbers, and the README's tool
and resource list.

## 11. Owner questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Instructions as §3 (steps, kinds, guide URIs, rules), about 1,040 characters | Yes |
| Q2 | The guides as resources rendered from the prompt files with `<game>` / `<ply>` (no new files) | Yes |
| Q3 | `definitions`' query of several words and the `kinds` answer, in the same packet | Yes: the trial spent nine calls there |

## 12. Review dispositions — rev. 1 (`69e7d1b`), independent review: NOT_READY

| # | Finding | Disposition |
| --- | --- | --- |
| B1 | The design assumed every host gives its model the instructions; MCP leaves it to the host | §2 (new): the four host settings, what Calliope guarantees, the supported setting (instructions to the model and resources readable), HIMARI as a supported host. G5; G6 puts the essentials in the tool descriptions, the one channel every host passes. Tests split: §9 checks what Calliope sends, §8's trial the host integration. The intro no longer calls the instructions "the one text every host gives the model". |
| B2 | Without the guide, nothing told the kinds (`judgement`) from the registry's ids (`proposition.judgement`) and class (`proposition`) | The instructions say it (§3); `submit_commentary`'s description lists the kinds from the verifier and says how to find a kind's fields (§5.2) — it pointed to `proposition.*`, very likely where the trial's agent took the ids from; the refusal of a prefixed kind says what to write (§5.3, G7). |
| N1 | Acceptance leaned on tool use | §8: evidence judged by what the commentary says, no call required for its own sake; the accepted commentary is read; three turns. Step 3 of the instructions says the same ("where `ply`'s claims are not enough"). |
| N2 | Guidance changes were not traceable | §6: `guidance: agent_guidance_v1` in the agent build, pinned by a test; reasoning build and cache keys unchanged. |

## 13. Review dispositions — rev. 2 (`54a24ac`), re-review: READY_FOR_MERGE

B1, B2, N1 and N2 confirmed resolved. Two minor notes, applied here:

| # | Note | Disposition |
| --- | --- | --- |
| N3 | A query of several words looked at the id and the statement only; `grade` and `move` are field names | §5.1: a query of several words matches the id, the statement and the field names together; a one-word query as today. §9 tests the trial's `"proposition move grade"`. |
| N4 | The guidance version's pin covered the instructions and descriptions, not the search | §6: the search is pinned by its own tests (§9), and a change to it is a change of the guidance. |

