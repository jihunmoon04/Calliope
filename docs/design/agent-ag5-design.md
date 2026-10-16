# Agent — AG5-D design: guidance an agent reaches by itself

Status: **rev. 1 — draft for independent review**. Date: 2026-10-16. Base: `main @ dfbf8d7` (AG4-D
AM1 merged). The trial's host faults are fixed in HIMARI first (its PRs #44, #45), so a repeat measures Calliope's guidance. Inputs: [`agent-mcp-design.md`](agent-mcp-design.md) (AG-D: §2 the shape, §6 the
prompts, §7 resources and registries, §10 build identity); MCP 2025-11-25 (server features: tools
are model-controlled, resources application-driven, prompts user-controlled; resource
annotations); a live trial in HIMARI v3 (2026-10-16, §0).

Calliope tells an agent how to reason and how to check itself in two MCP prompts (AG-D §6). A
prompt is chosen by the **user**: the specification calls prompts user-controlled, and a host does
not let the model open them. The server's `instructions` — the one text every host gives the model
— end by sending the agent there: "자세한 방법은 프롬프트 calliope_commentary와 calliope_check, 용어는
calliope://glossary/ko에 있습니다". An agent that was not handed the prompt by its user has no way to
the method, and goes looking for it.

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
| G1 | **Each MCP feature in its role.** The `instructions` give the minimal working order and the exact URIs of the method; **resources** hold the method in full, for the agent to read when it writes; **prompts** stay, the same method for a user who picks it; **tools** do the work. No agent loop in Calliope: the host's agent plans, Calliope serves facts, judgements, checks and the method. |
| G2 | **The method as two resources**, `calliope://guides/commentary_ko` and `calliope://guides/check_ko` (§3), rendered from the same files as the prompts (`agent/prompts/commentary_ko_v1.md`, `check_ko_v1.md`): one source, so a resource and its prompt never differ but for the target. The files, their digests, the prompt ids and the agent build (AG-D §10) are unchanged. |
| G3 | **New `instructions`** (§2): what Calliope is, the order of one commentary in four steps, the two guide URIs and that the agent reads them before writing, that the prompts are the same method for the user, and the rules that must hold even if the guides are not read. A host that shows no resources still gets a working order. |
| G4 | **`definitions` finds what an agent asks for** (§4): a query of several words matches the entries that contain every word; an unknown kind answers with the kinds there are. Arguments and tool names are unchanged; the answer gains one field only when a kind matches nothing; `TOOLS_VERSION` stays `agent_tools_v3` (as AG4: names and arguments unchanged). |
| G5 | **Not changed:** the prompts (names, arguments, text), the registries and their digests, tool answers other than §4's field, the viewer. Not added: a tool that serves the method (the resources do, and a host that cannot read resources still has G3); method links in tool answers (§6). |

## 2. The instructions

Replaces `INSTRUCTIONS` in `agent/server.py` (about 760 characters; HIMARI gives a server up to
4,000):

```text
Calliope는 체스 수를 엔진과 사실 근거로 판정하고, 에이전트가 쓴 해설을 그 근거와 대조해 받아들이는 서버입니다.
해설은 이 서버가 준 정보로만, 한국어로 쓰세요.

한 수를 해설하는 순서:
1. open_game으로 게임을 엽니다(PGN, 또는 fen과 moves). 받은 게임 id를 계속 씁니다.
2. ply로 그 수의 등급·라벨·최선수·클레임을 읽습니다. 두지 않은 수는 judge_move로 판정합니다.
3. 쓰려는 근거를 facts·explore·judge_move로 확인합니다. "왜"는 비교로 답합니다: 더 나은 수가 하고 이 수가 하지 못한 것.
4. 확인한 것을 명제로 만들고 문장마다 명제를 인용해 submit_commentary로 제출합니다. 거부되면 표시된 곳을 고쳐 다시 제출합니다.
판을 사용자에게 보여 주려면 show_game을 씁니다.

해설을 쓰기 전에 리소스 calliope://guides/commentary_ko(방법: 명제 형식, 수·숫자 표기)를, 제출 전에
calliope://guides/check_ko(점검 목록)를 읽으세요. 용어는 calliope://glossary/ko, 모르는 정의는
definitions로 찾습니다. 프롬프트 calliope_commentary·calliope_check는 같은 지침을 사용자가 고를 때 쓰는 것입니다.

꼭 지킬 것: SUPPORTED라도 ATTRIBUTED가 실패한 득실은 이 수의 성과가 아닙니다. specific_line은 한 라인에서만
성립하고, 패턴은 배치일 뿐입니다. 직접 탐색한 라인(by: agent)은 엔진의 라인이 아닙니다. 숫자·수·칸은
인용한 명제의 값만 씁니다.
```

- **Steps, not prose.** The four steps are AG-D §6's method in its own order (`ply` first, then
  checking by comparison, then propositions and submission), short enough to act on without the
  guides.
- **The exact URIs, and when to read them.** "Read before writing" and "before submitting" tie
  each guide to its step. Naming the prompts once, as the user's way to the same method, removes
  the reason to look for them; a prohibition ("do not guess URIs") is not needed when the real
  ones are given.
- **The rules that must hold** stay in the instructions (they were there): the server cannot check
  the wording (AG-D §6), and an agent that skips the guides must still not break them.

## 3. The guide resources

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
- **Why resources.** The specification's model is that resources are context the host provides to
  the model as it decides; a host may expose them to its model (HIMARI's `read_resource`, Claude
  Code's resource tools) or let the user attach them. Either way the agent receives the same text
  as the user who picks the prompt.
- **Annotations.** `audience: ["assistant"]` says the guide is meant for the model; a host that
  ranks resources may use `priority`. Neither restricts anything.
- **Listed, not templated.** The guide does not depend on the game, so a fixed URI is enough; the
  agent already knows its game and ply.

## 4. `definitions`

| Input | Today | AG5 |
| --- | --- | --- |
| `query` of one word | entries whose id or statement contains it (case-insensitive) | unchanged |
| `query` of several words | the whole string as one substring (usually nothing) | entries whose id or statement contains **every** word |
| `kind` that no entry has | `{"definitions": [], "total": 0, "limit": 40}` | the same, plus `"kinds"`: every kind there is, sorted |

- The tool's description names the common kinds (`proposition`, `use`, `sentence_class`,
  `token_rule`, `check`, `prompt`) and says that an unknown kind answers with the list.
- `ids` lookups, limits, ordering and every other answer are unchanged.

## 5. Tests

- **Instructions:** the server's `initialize` result carries the new text; it names
  `calliope://guides/commentary_ko`, `calliope://guides/check_ko`, `calliope://glossary/ko` and the
  tools `open_game`, `ply`, `judge_move`, `facts`, `explore`, `submit_commentary`; every URI it names
  is listed by `resources/list`.
- **Resources:** `resources/list` lists both guides with their MIME type and annotations;
  `resources/read` of each returns the prompt's text with the target `<game>` / `<ply>` — the same
  as `prompts/get` with `game="<game>"`, `ply="<ply>"`, character for character; no `{` or `}` is
  left doubled.
- **Build:** `agent_build()` is unchanged (the prompt files and the registries are not touched).
- **`definitions`:** a two-word query finds the entry that holds both words and not the ones that
  hold one; a one-word query answers as today; an unknown kind answers `kinds` (all 26 today,
  sorted) and an empty list; a known kind has no `kinds` field.

## 6. Considered and left out

- **A tool that returns the method** (e.g. `guide`). Every host shows tools, so it would reach more
  hosts than a resource. It duplicates the resources and the prompts with a third surface; G3 already
  gives every host the working order. Reconsider if a host that cannot read resources needs the full
  method.
- **Method links in tool answers** (an MCP `resource_link` in `open_game` or `ply`). It would point
  to the guide at the moment it is needed, but changes the answers of tools whose JSON is fixed
  (AG-D §3) and is redundant with G3.
- **Putting the whole method in the instructions** (about 2,500 characters). It would be in every
  request of every conversation, also when the agent only shows a game; some hosts cut long
  instructions. The four steps and the rules are what an agent needs before it reads anything.

## 7. Acceptance: the trial again

After AG5, the trial of §0 is repeated with the same host, model, game and ply, and recorded here.
Measured per turn: Runs, input tokens per Run and in total, cached input tokens where the provider
reports them, the calls in order, the Run of the first `judge_move` or `facts`, and whether
`submit_commentary` was accepted.

| Measure | Target |
| --- | --- |
| Guessed URIs read, prompts looked for | 0 |
| Guide read | `calliope://guides/commentary_ko` read before submitting |
| Ply analysed | 10 (5...h6) |
| Reasoning | `judge_move` or `facts` used; `explore` where the comparison needs it |
| Propositions | kinds as the guide writes them (`judgement`, not `proposition.judgement`); a refusal corrected on the next submission |
| Commentary | `submit_commentary` accepted, stored, shown by `commentary` |
| Runs | within 8 (an experimental target, not yet known to be reachable) |
| Cost | input tokens compared with §0 |

If the agent still searches or repeats itself, that is the host's to bound (HIMARI's run limit and
loop control are HIMARI's design work), and recorded here as found.

## 8. Packet

One implementation packet, **AG5**: `agent/server.py` (instructions, the two resources),
`agent/build.py` (the guide rendering beside `text`), `find_definitions` (§4) and the
`definitions` tool's description, the tests of §5, the trial of §7 with its numbers, and the
README's tool and resource list.

## 9. Owner questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Instructions as §2 (steps, guide URIs, rules), about 760 characters | Yes |
| Q2 | The guides as resources rendered from the prompt files with `<game>` / `<ply>` (no new files, build unchanged) | Yes |
| Q3 | `definitions`' query of several words and the `kinds` answer, in the same packet | Yes: the trial spent nine calls there |
