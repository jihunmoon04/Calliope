# Agent — one meaning once: duplicates and the default digest (MS framing)

Status: **framing, rev. 3, for the owner — no design decision, nothing to implement; owner
questions in §7; independent review READY_WITH_CORRECTIONS (B1, B2; N1, N2) applied, §9; rev. 3:
§2.3 measured relation by relation (owner, 2026-10-18)**. Date: 2026-10-18. Base: `main @ feac72f` (AG8 merged).
Inputs: [`agent-ag8-design.md`](agent-ag8-design.md) (AG8-D: `board`, `part`, `proves`),
[`agent-ag8-implementation.md`](agent-ag8-implementation.md) (§4 the acceptance trial),
[`agent-commentary-path.md`](agent-commentary-path.md) (the AG8 framing note), R0-D/R2-D (the
reasoner's rounds and catalogue).

The owner's direction after AG8 (2026-10-18): **keep every kind of data; put together what says
the same thing twice; cut structure that is not needed.** Data that today's move commentary does
not use is kept when another kind of commentary could use it, and leaves the default digest
instead of the system. The owner also asked whether the reasoner's rounds should go. This note
gives the measurements behind both, and the packet's scope (MS) for the owner to settle.

## 1. What was measured

- **Use**: the AG8 trial's records — 38 runs on AG8 (rev. 1 and rev. 2: luna and Haiku, four
  games), 195 saved commentaries, each traced to the digest it was written from (the last `ply` or
  `judge_move` digest of its position); every cited proposition mapped to the digest field it came
  from (a claim and a line by handle, a board proposition by content). `main`'s 16 runs (AG7) for
  the tools only.
- **Rounds**: every ply of four games analysed again on one engine, in variants (§3): today's
  runner twice (a control: 111 of 111 plies the same, the engine is deterministic here), with every
  family computed first, with four rounds, with a mechanism's reads requested at once.

## 2. Use

### 2.1 Served → cited

For each digest field (or claim template), the saved subjects whose digest had it, and how many of
those cited it:

| Most used | | Least used | |
| --- | --- | --- | --- |
| `judgement` | 190 / 195 | `lines.others` (the other candidates) | 1 / 195 |
| `mate_found_v1`, `mate_allowed_v1` | 13/14, 12/14 | `refuted` (REFUTED claims named) | 0 / 195 |
| `newly_exposed_v1` | 9 / 12 | `sacrifice_offer_v1`, `sacrifice_sound_v1`, `sacrifice_compensated_v1` | 1, 1, 0 / 20 |
| `forcing_v1` | 24 / 34 | `mate_in_one_allowed_v1` | 0 / 7 |
| `check_answer_v1` | 11 / 16 | `board` threat `check` | 2 / 35 |
| `piece_offer_v1` | 31 / 48 | `discovery_v2` | 1 / 12 |
| `board` threat `attack` | 34 / 53 | `missed_gain_v1` | 31 / 146 |
| `capture_holds_v1` | 27 / 48 | `en_passant` (text, not citable) | — / 4 |
| `board` `lost_defence` | 42 / 83 | | |
| `better_alternative_v1` | 75 / 146 | | |

The counts are digests over runs, and one fixed moment is read in up to eleven runs: the 20
sacrifice digests are two moves (13.Rxd7 and 16.Qb8+ of the Opera Game), and each relation claim
of §2.3 is one move.

Where the digest's characters go (mean of 199 digests): `claims` 40% (their `findings` the
largest part: 221 characters a claim), `board` 24%, `lines` 11%, `refuted` 7%, `text` 5%,
`not_shown` 4%; the rest under 2% each.

### 2.2 Read but not cited

The texts no sentence can cite — a claim's `says` and `proves`, a board item's `proves`,
Calliope's `text` — are read: of a sentence's character trigrams, 7–16% are found in the text of
an item it cites (`says` 0.07, board `proves` 0.10, `text` 0.10, claim `proves` 0.16), against
0.3–1% for a text of another subject drawn at random. The agent paraphrases them; a low citation
count is not disuse.

### 2.3 The same relation twice — where it is one

In the trial's digests, the relation claims came with a `board` item in every digest that had them
(`removed_defender_v2` 12 of 12, `fork_v2` 9 of 9, `newly_exposed_v1` 12 of 12, `discovery_v2`
12 of 12) and `left_en_prise_v2` never (0 of 12). These are digests over runs: each claim is
**one move** read in many runs (`removed_defender_v2`, `discovery_v2` and `left_en_prise_v2`
31...Qf6 of the new game, `newly_exposed_v1` 38...Rxh5, `fork_v2` 13.Rxd7), and the same digest is
not the same relation (review B1). Every ply of the four games (233) analysed again, with each
supported relation claim set beside its digest's `board` (pieces by square at the claim's node,
the node as plies from the subject's move, the claim's relations):

| Claim | Move | Where its relation is | On the board | Link to the consequence |
| --- | --- | --- | --- | --- |
| `removed_defender_v2` | 31...Qf6 | the move (f8's defence of f5 blocked) | **the same**: `lost_defence` f8→f5 | `associated_with` |
| `newly_exposed_v1` | 38...Rxh5 | the move (the rook into the g4 pawn's attack) | **the same**: weakness h5 | `explains` |
| `fork_v2` | 13.Rxd7, 33...Bd6 | the move | **the same**: the double attack, same actor and targets | `associated_with` |
| `fork_v2` | 12.O-O-O | the engine line, 2 plies on | none | `associated_with` |
| `pin_v2` | 6.Bc4, 12.Qc1 | the engine line, 1–2 plies on | none | `associated_with` |
| `discovery_v2` | 31...Qf6, 31.Kg1 | the engine line, 1–6 plies on | none (the board's attack f6→d4 is another relation) | `explains`, `associated_with` |
| `left_en_prise_v2` | 31...Qf6, 34.Qxd6 | before and after the move (it held) | none (the board serves changes) | `explains`, `associated_with` |

Eleven supported relation claims in 233 plies; five of them, at four moves, are a board item's
relation. What differs:

- **At the move** (`removed_defender_v2`, `newly_exposed_v1`, `fork_v2` at the move), the relation
  is the board item's; the two say different things about it. The board item says **what the
  move changed**: which piece lost which defender and what attacks it now, with the counts —
  whether or not that piece is lost later. The claim says **what it led to**: the piece is the one
  the line wins (`removed_defender_v2`), the move exposed the piece lost (`newly_exposed_v1`), the
  double attack won material rather than standing as a configuration (`fork_v2`). The agent cited
  the relation through the board (`lost_defence` 42 of 83, `removed_defender_v2` 3 of 12).
- **In the engine line** (`fork_v2`, `pin_v2`, `discovery_v2` one to six plies on), the claim is
  the line's tactic after the move, which the board, reading the positions around the move, cannot
  state. Mostly `associated_with` — it comes with the consequence; it is not its cause.
- **Held** (`left_en_prise_v2`): a piece that could be won before the move and still can; no change,
  so no board item.

Three groups of claims say one thing with different evidence:

- "a better move": `better_alternative_v1` (the judgement: rank 1 was better), `better_move_v1`
  (it avoids the consequence: the material lost, the mate allowed), `missed_gain_v1` (it beat the
  played move by at least `MISS_LOSS`; grounds the MISS label). The agent cited them 75, 35 and 31
  times, often one in place of another.
- "the move offers material": `piece_offer_v1` (LV-D, the brilliant rule's) and
  `sacrifice_offer_v1` (R2-D), with `sacrifice_sound_v1`; at the two sacrifices the agent cited
  `piece_offer_v1` 31 times, the sacrifice claims twice.
- "the move allows a mate": `mate_allowed_v1` and `mate_in_one_allowed_v1` (exact, without a
  judgement); the second cited 0 of 7, the first 12 of 14.

### 2.4 What the agent made itself

Eleven `attack` propositions cited were no board item. Nine state a standing relation — seven at
the position before the move, two after it but there before as well: "the queen on f3 and the
bishop on c4 both aim at f7" (6...Nf6 of the Opera Game, in four runs), "the pawn on g4 was a target"
(28...Qe6). Two are the attacker of the piece just moved (15.Bxd7+, 38...Rxh5), which the board
serves as an exposed weakness, not as an attack (15.Bxd7+'s since AG8 rev. 3). The agent wants the position's standing relations as the setting of a move; `board`
serves only changes, and nothing serves the setting.

### 2.5 Tools

With `board`, `facts` calls fell from 2.7 to 0.4 a run and `definitions` from 1.8 to 0.8
(`main` against AG8); `detail` stayed rare (0.1–0.2).

### 2.6 What this measurement cannot say

Four games, fixed moments chosen for their mistakes, two models; how often a field is cited follows
what the guide asks the agent to cite, so a low count says what today's move commentary uses, not
what the data is worth; the trigram measure is coarse.

## 3. The rounds

### 3.1 With every fact computed first

Every family on every node of the tree before round 0 (and on the nodes a later round adds), on
the Opera Game (33 plies) and the new game (78):

| | Today | Facts first |
| --- | --- | --- |
| Plies with a round after round 0 | 65 / 111 | 3 / 111 |
| Claims decided after round 0 | 155 | 6 (`piece_offer_v1` 3, `capture_holds_v1` 3) |
| Claims the same as today | — | 110 / 111 plies |

The three plies are offers of the Opera Game, whose capture of the offered piece is searched (a
line need, `SURVEY`); the new game has none. The ply that differs is 11.Bxb5+: today `fork_v2`,
`pin_v2`, `skewer_v2`, `discovery_v2` close INCONCLUSIVE at the round limit; with the facts first
the fork is SUPPORTED and the others REFUTED. Computing everything first costs 63–72% more time,
70% of it `exchange` (about 1 s a ply); every other family together about 0.4 s a ply on trees of
about 200 nodes.

### 3.2 Why a later round decides more

At 11.Bxb5+: round 0 proposes `material_gain_v3`, which needs `exchange` on 13 nodes; in round 1
it is SUPPORTED, and only then are the mechanisms that would explain it proposed (a mechanism
rests on a SUPPORTED consequence); `fork_v2` needs `pattern_delta` on one node of the line; that
node has no fork, so in round 2 it needs the next node; in round 3 it finds the fork — one round
too many at `max_rounds` 3. Nothing new exists in a later round: the same facts are asked for in
small steps, and the rounds bound how long that chain may be. With four rounds the ply is decided
as with the facts first (the other 32 plies unchanged, 55.0 s against 55.3 s).

### 3.3 A mechanism's reads at once

A mechanism (`_Mechanism.verify`) scans its line node by node and stops at the first node whose
records are missing. Asking for its `reads` on every node of the scan at once:

| | Opera Game (33) | Rapid (55) |
| --- | --- | --- |
| Plies decided as with the facts first | 33 (11.Bxb5+ now decided) | 55 |
| Claims closed at the round limit | 4 → 0 | 0 → 0 |
| Family needs admitted | 147 → 151 | 154 → 154 |
| Time | 58.7 s → 59.1 s | 122.8 s → 122.6 s |

The scan is short (to the decisive capture) and its families are the cheap ones; `exchange` is not
among a mechanism's `reads`. A candidate's own check (`pieces`, `exchange` on one node) stays one
at a time.

### 3.4 What the rounds are, and whether they should go

The rounds are lazy evaluation in dependency order: a family is computed when a template asks for
it, a mechanism after its consequence. They are not visible to the agent, and they cost less than
computing first. The one loss measured comes from asking in small steps, and §3.3 removes it at no
cost. Removing the rounds would rewrite the runner, the needs and the catalogue's ten modules, and
change the reasoning build (every cached analysis recomputed) for nothing the owner's direction
asks. **They stay**; the question returns when many templates are added for other kinds of
commentary (pawn structure, king safety), where a template that reads prepared facts is easier to
write than one that asks for them.

## 4. `sacrifice_compensated_v1`

It asks whether the sacrifice got a concrete return: the played line ends in a mate that every
line keeping the material does not reach, or wins back more material than each of them. At both
sacrifices it is INCONCLUSIVE with `LINE_TOO_SHORT`: one keeping line's PV ends inside an exchange,
so its material outcome is open, and the rule decides only when every line is.

| Move | Played line | Keeping lines |
| --- | --- | --- |
| 13.Rxd7 | material +3 | rank 3 **open**, rank 4 ±0 |
| 16.Qb8+ | **mate** | ranks 2 and 3 ±0, rank 4 **open**, rank 5 −1 |

Over every ply of the four games (233: 33, 55, 78 and 67), `sacrifice_offer_v1` is SUPPORTED at 4 moves and
`sacrifice_compensated_v1` decided at two of them (one SUPPORTED, one REFUTED): the rule works
where every line is decided; the two INCONCLUSIVE are the Opera Game's. At 16.Qb8+ the open line's
engine score is +1.27 for White, no mate, while the played line mates in two: the outcome is
decided by the score alone. At 13.Rxd7 the open line scores +5.00 against the played +6.50, but the
rule compares material, which a score does not give.

**Owner decision (2026-10-18): in MS**, a played mate is strictly above a keeping line whose
material is open when that line's engine score is no mate for the mover (the rule reads the
outcome only today). A score without a mate does not prove that no mate exists in that line (review
N1): it is the engine's evaluation, not a decided outcome. The verdict says which it rests on — a
finding of the mate decided by the outcomes as today, or one decided by a keeping line's score — so
a reader (and a label rule) can tell them apart; no new sacrifice rule beyond that. 13.Rxd7, which compares material, stays open: extending an open line by a
search is left until its cost is measured.

## 5. The packet (MS)

| # | What | From |
| --- | --- | --- |
| MS1 | A mechanism's `reads` requested on the whole scan at once; `max_rounds` stays 3 | §3.3 |
| MS2 | A relation and what it leads to, apart (review B1, §2.3): a **relation** (kind, pieces by identity, its place — the move, or ply k of an engine line — and its time, MS3) is stated once; a relation **claim** becomes a link from a relation to the consequence it comes with (`explains`/`causes`, or `associated_with`), and whether the relation did anything (a fork that won material, not a configuration). At the move, a board item and a claim are one relation only when kind, pieces, place and time are the same (§2.3: five of eleven); a relation in the engine line or one that held is stated with its place or its time, which the board cannot give today. Every claim template and its verdict stay | §2.3 |
| MS3 | A relation's time: **began** (today's board), **holds** (stood before and after: `left_en_prise_v2`'s piece; the setting the agent built itself), **ended** (a lost defence); and its place (MS2) | §2.3, §2.4 |
| MS4 | The three groups of §2.3 as one meaning each with its variant and evidence ("a better move" by judgement / by consequence / by margin; "offers material"; "allows a mate"); every claim and label rule stays, the digest shows one | §2.3 |
| MS5 | `sacrifice_compensated_v1` decides a mate against an open keeping line by its score, and its finding says it rests on a score (review N1) | §4 |
| MS6 | The default digest smaller, nothing deleted: `lines.others` and `refuted` behind `detail` (counts stay), `findings` replaced by `proves` where a claim has one, and the simplification agreed after AG8 (cite by handle; `proves` in place of `text`/`says`; the agent no longer writes `use`) — as far as §7 Q3 settles. **`part` does not replace `use`** (review B2): `part` says what a remark does in the commentary and is shown; `use` is checked (`Verifier._use`: a result only of a consequence and only when its ATTRIBUTED check passed; a mechanism only with an `explains`/`causes` relation to a SUPPORTED claim; `associated` only for an `associated_with` claim; `uncertain` only for INCONCLUSIVE; `not_the_case` only for REFUTED). If the agent stops writing `use`, the server derives the roles a cited claim may take from its verdict, its relations and its checks, and a sentence that says more than they allow is still refused or noted: the agent's input gets simpler, the check keeps its meaning | §2.1, §2.2 |
| MS7 | The trial again: this note's measurements before and after, and AG8's fixed moments (wrong sentences no more, reasons cited no fewer, a smaller digest) | §1 |

Kept as they are: every fact family (`king`, `pawns`, `squares`, `lines` and `draw` are read by
neither the board nor most templates, and are what commentary on structure, king safety or
endgames would read); every claim template and label rule; the rounds.

## 6. Not in this packet

- Removing the rounds (§3.4).
- New kinds of commentary (candidate moves, why-not, structure, brilliancies). MS should let a
  kind choose what it reads from one store of meanings, with today's move commentary the default
  view: `lines.others` would serve candidate moves, `refuted` a why-not, the sacrifice claims a
  brilliancy, the unused families structure and king safety.
- Extending a keeping line by a search for `sacrifice_compensated_v1` (§4).

## 7. Owner questions

1. **Where one relation lives** (MS2): in the reasoning layer, as a meaning the board shows, or in
   the agent's `board`, with the claims pointing at it? Recommended: the reasoning layer — it is
   where the claims and their relations are, and AG8 already moved `lost_defence` onto the fact
   engine's `pattern_delta`; `board` becomes a view of it.
2. **The setting** (MS3): the standing relations before the move (what aims at what) in this
   packet, or only `holds` for the pieces a claim is about (`left_en_prise_v2`), the setting later?
   Recommended: the latter; the setting needs its own limits (a position has many standing
   relations) and is closer to a new kind of commentary.
3. **The simplification agreed after AG8** (MS6): all of it in MS, or `proves` now and the rest
   later? Recommended: all, with the server's derivation of a claim's roles (MS6) settled in MS-D
   before the agent stops writing `use` — never `part` written for `use`.
4. **The groups of §2.3** (MS4): one claim with variants (fewer templates; the label rules read the
   variant), or the templates kept with the digest showing the strongest one? Recommended: kept,
   shown once — no label rule or cached analysis changes.

## 8. The evidence

Scripts and outputs of this note (session scratchpad, not in the repository): `measure.py`
(§2), `probe_eager.py` and `probe_famcost.py` (§3.1), `probe_rounds4.py` and `probe_trace21.py`
(§3.2), `probe_batch.py` (§3.3), `probe_sac.py` and `probe_sac_all.py` (§4), `probe_pairs.py`
and `pairs_report.py` (§2.3, rev. 3).

## 9. Review (rev. 2)

Independent review of rev. 1: READY_WITH_CORRECTIONS — the direction and the rounds kept agreed;
MS1 enough grounds; MS2 and MS6 change the contract of facts and evidence, not just their size.

| Item | Applied |
| --- | --- |
| B1 — the same digest is not the same relation | §2.3 says what the counts are; MS2 links a board item and a claim only when pieces, kind, node and time match, keeps the claim's causal link apart, and measures the pairs first |
| B2 — `part` cannot replace `use` | MS6: `part` is shown, `use`'s checks move to the server's derivation of a claim's roles; Q3's recommendation |
| N1 — a score without a mate proves no absence of a mate | §4 and MS5: the finding says whether the mate's superiority rests on outcomes or on a score |
| N2 — 221 plies | 233 (33, 55, 78, 67); the 221 was a sum done wrong, every ply was analysed |

The review's answers to §7 agree with the recommendations: Q1 the reasoning layer, the fact
apart from the claim's causal reading; Q2 `holds` for a claim's pieces only; Q3 possible once the
server's derivation is settled; Q4 the templates and label rules kept, shown once, each one's
evidence reachable.

Rev. 3 (owner, 2026-10-18: which of the pairs are one relation, what differs, and whether each is
needed): §2.3 measured relation by relation over the 233 plies — the trial's 12-of-12 counts were
one move each over many runs; five of the eleven supported relation claims are a board item's
relation, the rest a tactic in the engine line or a relation that held. MS2 now separates the
relation (with its place and time) from the claim's link to the consequence, so the three cases
take one form.
