# Agent — the commentary path end to end: the question (AG8 framing)

Status: **framing, rev. 1, for the owner — no design decision, nothing to implement**. Date:
2026-10-18. Base: `main @ 392646a` (AG7 merged).
Inputs: [`agent-mcp-design.md`](agent-mcp-design.md) (AG-D: §4 propositions and uses, §5.3 the
sentence check), [`agent-ag6-design.md`](agent-ag6-design.md) (AG6-D: the digest),
[`agent-ag7-design.md`](agent-ag7-design.md) (AG7-D: §0 the trials, §8 next),
[`agent-ag7-implementation.md`](agent-ag7-implementation.md) (the acceptance trial, Appendix B).

AG7-D §8 left two things for later: the board's facts and the same-reply comparison as citable
items with the ply (C′), and the owner's question about the whole path — what the agent is given,
in what shape, and what it is asked — so that the model understands what a remark means and what
its evidence proves, and acts as intended, instead of being told afterwards what not to write.
This note takes both together. It describes the path as it is (§1), what about 110 trials and the
AG7 acceptance runs show (§2), the gaps (§3), three directions (§4), and a first step (§5). The
owner's questions are in §6.

## 1. The path today

| Step | What the model is given | What it is asked | What is checked |
| --- | --- | --- | --- |
| Guidance | the server instructions; `calliope://guides/commentary_ko` (`commentary_ko_v2`): three kinds of statement, a table of twelve remarks with the evidence each needs, lengths | write like a commentator; cite; say readings as readings | nothing |
| `analyze_game`, `game_overview` | the moments of the game (grade, label, score per ply) | choose the moments | nothing |
| `ply` (the digest, AG6-D §3) | grade, label, scores, FEN before and after, the played and best lines (8 plies of SAN), three other candidates' scores, Calliope's `text`, the claims (template, role, status, scope, `says`, findings), the REFUTED claims by name; 3–4k characters on average, bound 16k | — | — |
| `facts`, `explore`, `judge_move`, `detail` | on request: a position's fact records (`pieces` is one record per piece: attacks, attackers, defenders, pins), a line the agent plays, a move's judgement, a claim's evidence | the guide's table says when to use them | — |
| Propositions | 16 kinds; `judgement` and `claim` by handle, the others field by field (`attack`, `pin`, `engine_line`, `explored_line`, …) | build one for each thing a sentence says | every field equals what the session served (AG-D §4) |
| Sentences | — | `{text, class: sourced \| interpretation, cites}` | S1–S6: every move, score, mate, square and number in the text is in **some** cited proposition (AG-D §5.3); the wording is not checked; the class is the agent's own declaration |
| Stored, shown | — | — | level `SOURCE_VERIFIED`; an interpretation is shown as the agent's reading |

The only statement of what a claim *means* that the agent sees is Calliope's own sentence (`says`,
`text`) and the template's definition behind `definitions`. A claim's `use` (result, line_fact,
mechanism, comparison, …) says how a commentary uses the claim, but it is not tied to any
sentence: the check reads the union of all cited propositions.

## 2. What the trials show

AG7's acceptance runs: luna (`openai/gpt-6-luna`), three runs of each of two games on the AG7
branch, now `main` (AG7 implementation §4, Appendix B). The earlier trials: AG7-D §0.

**F1 — every sentence cites, and what it cites is Calliope's conclusions.** 106 sentences, none
without a citation. Cited: 126 claims, 76 judgements, 4 engine lines, **no board fact and no
explored line**. Before AG7 the same held (47 sentences: 70 claims, 47 judgements).

**F2 — fetching facts is not using them.** Three of the six runs called `facts` (11 calls, each
answer 13–22k characters of per-piece lists, one to four families). No `attack`, `pin`, `pattern`
or other position proposition was submitted in any run. The answer is the whole board's raw
relations; which of them matter to the move is left to the agent, and nothing in the check asks for
one. (In AG7-D's pre-check luna did cite `pin` and `attack`, when a sentence named a square that only
a fact could cover: the tools are used when the check forces it, §0.2 of AG7-D.)

**F3 — a reason served plainly is said; one that needs reading is not.**
Over the three runs of each game (served = digests that carried the claim; cited = commentaries
that cited it; a commentary may cite a claim served with another ply):

| Claim | Opera: served / cited | Rapid: served / cited |
| --- | --- | --- |
| `fork_v2` (13.Rxd7 attacks a7, e7, d8) | 4 / 3 | — |
| `mate_found_v1`, `mate_allowed_v1`, `mate_delivered_v1` | 5 / 5 | 10 / 11 |
| `better_alternative_v1`, `missed_gain_v1` ("X was better") | 18 / 8 | 48 / 24 |
| `sacrifice_offer_v1`, `sacrifice_compensated_v1`, `sacrifice_sound_v1` | 21 / 0 | — |
| `only_move_v1` | 5 / 0 | 4 / 0 |
| `prevents_v1`, `rescue_v1` | — | 4 / 0 |
| `material_gain_v3`, `material_loss_v2` | 17 / 7 | 31 / 0 |

The one backed "why" the acceptance found on every run (13.Rxd7's fork) is a claim the server made
and named. Claims whose meaning is subtler (a sacrifice that is compensated, an only move, a move
that prevents something) were served and never used.

**F4 — the link between a sentence and its evidence is lexical.** In the rapid game 18 of 26
interpretation sentences cite only the subject's judgement and an "X was better" claim — the same
two items the sentence before them cites — and say something neither proves ("had the queen gone
to a safe square, White's pressure would have eased"; "it was a pity not to take the concrete
chance"). In the Opera Game 4 of 32 sourced sentences end in a reading their citations do not
support ("Black needed to tidy the queen first, given White's attack", citing `missed_gain_v1`,
which says only that 6...Qd7 was better). The check passes both: the tokens are covered, and the
class is the agent's word.

**F5 — the "why" of many mistakes is a comparison no claim states.** At 5...h6 (AG5's trial) the
reason is that after 5...Bc5 the same 6.Bxc6 dxc6 7.Nxe5 meets 7...Qd4, after 5...h6 only 7...Qe7.
The comparison claims say that the other move is better (`better_alternative_v1`,
`missed_gain_v1`, `better_move_v1`); `best_stops_reply_v1` tests one square by static exchange.
No agent in about 110 trials was seen to play the reply after the best move itself; one
`explore` was cited in 37 runs (Sonnet).

**F6 — the model sets the ceiling, the data sets the shape.** luna < Haiku (about twice the cost)
< Sonnet (about thirty times) in concreteness and variety; removing Calliope's sentences did not
free the style — agents paraphrased the engine lines instead (AG7-D §0.1, set 2). What the digest
carries is what the commentary is made of.

## 3. The gaps

1. **Material.** What the agent can cite holds the verdict and the line, rarely the reason. Board
   relations come as raw records, not as "what this move changed"; the same-reply comparison is not
   offered at all (F2, F5).
2. **Meaning.** Nothing states, in a form the agent and the check share, what an item proves and
   what a sentence asserts. The check sees tokens; the class is self-declared; `use` is not tied
   to a sentence (F4).
3. **Behaviour.** The guide asks after the fact; the agent's working goal is the shortest
   submission that passes. Gathering evidence costs calls and is never required (F1, F2).

Gap 1 alone is C′. Gaps 2 and 3 are the owner's question. Fixing 1 without 2 risks F3's pattern:
items served and not used, or cited by a sentence that says something else.

## 4. Directions

### D1 — reasons in the digest (C′ as AG7-D §8 put it)

The server adds to the digest of each analysed ply, as citable items with handles:
- what the move changed on the board: attacks, double attacks and pins made or broken, pieces left
  without a defender, a check — the difference of the positions before and after, a short list,
  not the whole board (`pattern_delta`, `pieces`, `exchange` already compute these);
- the same-reply comparison: the reply in the played line that hurts, played after the best move
  instead, and what happens there (material, mate, a legal-move count; no search, like
  `best_stops_reply_v1`'s counterfactual node).

The check stays as it is.
- For: F3 and F6 — what is served with a reason in it is said.
- Against: F3 — serving is not using (sacrifice and only-move claims); F4 — a sentence can cite a
  change item and say something else.
- Cost: a selection rule and the digest's size bound; no new tool.

### D2 — remarks with meanings, and sentences that state them

D1's items and today's claims become *remarks*: each carries, as data, what it proves in a fixed
short form (the subject, the relation, the position or line it holds in, its scope: "in the
position after 13.Rxd7 the rook attacks a7, e7, d8"; "in the engine line only"), and the parts it
can play in a commentary (reason, consequence, comparison, context). A sentence states one remark
in one part — `use`, today a claim's, generalised and tied to the sentence. Then:
- the check reads a sentence's tokens against the remark it states, not against the union of its
  citations;
- an interpretation names the remark it reads from, and a reading of the grade alone is not a
  reading (F4's 18 of 26);
- a key moment whose digest has a reason remark states at least one (gap 3: the shortest path now
  runs through a reason).

The meaning lives in the data, not in the guide; the model's work is choosing, ordering,
connecting and phrasing. The wording itself stays unchecked.
- For: closes gaps 1 and 2 at the level of the remark, and gap 3 in part.
- Against: a vocabulary of remarks to design; a bigger schema for the model (F6: luna may
  struggle); commentary may lean on the remarks' shape (F6's "data sets the shape"), so the remarks
  should be facts with meanings, not sentences to translate.
- Cost: the largest of the three on the server; D1 is its data part.

### D3 — the agent proposes, Calliope verifies

A tool takes a hypothesis in a fixed vocabulary ("after X the reply Y wins material", "X stops
Y", "X is the only move", "the piece on e7 is overloaded") and runs it through the reasoner's
hypothesis contract (R0-D §8), answering SUPPORTED, REFUTED or INCONCLUSIVE with a claim handle the
agent cites like any claim. This is the commentator's own order — think, then check — and reuses
the reasoner.
- For: the most human path; the reasons are the agent's, not a list.
- Against: F1–F2 and F5 — agents do not test what they need not; a weak model forms weak
  hypotheses; each test costs engine budget; the vocabulary is D2's work again.
- Value: strong models, later.

| | Gap 1 material | Gap 2 meaning | Gap 3 behaviour | Server work | Depends on the model |
| --- | --- | --- | --- | --- | --- |
| D1 | yes | no | a little | moderate | little |
| D2 | yes (D1 inside) | at the remark | yes, by the key-moment rule | large | some |
| D3 | yes, if asked | yes, for what is tested | no, unless required | large (after D2) | much |

## 5. A first step

The directions build on each other: D1 is D2's data, D3 uses D2's vocabulary. Recommended: D2,
reached in stages, and **a trial before a design packet**, as AG7-D did. In a scratch copy of the
server (never `main`):

- the two acceptance games plus a game no annotator has published (the Opera Game is famous;
  models may recall its notes);
- the moments' change items and same-reply comparisons built for those games;
- arms: today (AG7); D1 (items in the digest, check unchanged); D2 (items as remarks with meanings,
  a sentence stating one remark, the key-moment rule);
- luna ×3 per arm and game, Sonnet ×1 for the ceiling; under $1 at the published prices;
- measured by hand as in AG7-D §7: backed reasons per key moment, interpretations that read from a
  reason, wrong sentences, refusals, cost.

Then AG8-D with what the trial shows.

## 6. Owner questions

- **Q1.** The direction: D2 in stages with the trial first (recommended), D1 only, or D3?
- **Q2.** Who picks the reason that matters at a moment — the server ranks the remarks, or the
  agent chooses among them?
- **Q3.** The wording stays unchecked in every direction (the check is deterministic). Is meaning
  at the level of the remark enough, or should a second reading of the text (the `calliope_check`
  prompt's role) be considered?
- **Q4.** The model the path is designed for: luna as the floor (the deployment's), or a stronger
  default?
- **Q5.** The evaluation: the hand count of AG7-D §7, or also a blind ranking of commentaries by
  the owner?

## 7. Not in this note

The viewer's display in HIMARI (fullscreen), deployment, HIMARI's model settings.
