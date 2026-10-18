# Agent — one meaning once: duplicates and the default digest (MS framing)

Status: **framing, rev. 1, for the owner — no design decision, nothing to implement; owner
questions in §7**. Date: 2026-10-18. Base: `main @ feac72f` (AG8 merged).
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

The 20 sacrifice digests are two moves (13.Rxd7 and 16.Qb8+ of the Opera Game) read in many runs.

Where the digest's characters go (mean of 199 digests): `claims` 40% (their `findings` the
largest part: 221 characters a claim), `board` 24%, `lines` 11%, `refuted` 7%, `text` 5%,
`not_shown` 4%; the rest under 2% each.

### 2.2 Read but not cited

The texts no sentence can cite — a claim's `says` and `proves`, a board item's `proves`,
Calliope's `text` — are read: of a sentence's character trigrams, 7–16% are found in the text of
an item it cites (`says` 0.07, board `proves` 0.10, `text` 0.10, claim `proves` 0.16), against
0.3–1% for a text of another subject drawn at random. The agent paraphrases them; a low citation
count is not disuse.

### 2.3 The same relation twice

Of the digests with a reasoning claim, those whose `board` has an item of the same relation:

| Claim | Board item | Both |
| --- | --- | --- |
| `removed_defender_v2` | `lost_defence` | 12 / 12 |
| `fork_v2` | threat `pattern` (double attack) | 9 / 9 |
| `newly_exposed_v1` | weakness `exposed` | 12 / 12 |
| `discovery_v2` | threat `attack` | 12 / 12 |
| `left_en_prise_v2` | weakness `exposed` | **0 / 12** |

The board says what the move changed; the claim says that the change explains a consequence (the
material lost). The relation itself is served twice. `left_en_prise_v2` is the exception: the piece
could be won before the move as well, which is no change, so the board has nothing.

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

Over every ply of the four games (221), `sacrifice_offer_v1` is SUPPORTED at 4 moves and
`sacrifice_compensated_v1` decided at two of them (one SUPPORTED, one REFUTED): the rule works
where every line is decided; the two INCONCLUSIVE are the Opera Game's. At 16.Qb8+ the open line's
engine score is +1.27 for White, no mate, while the played line mates in two: the outcome is
decided by the score alone. At 13.Rxd7 the open line scores +5.00 against the played +6.50, but the
rule compares material, which a score does not give.

**Owner decision (2026-10-18): in MS**, a played mate is strictly above a keeping line whose
material is open when that line's engine score is no mate for the mover (the rule reads the
outcome only today). 13.Rxd7, which compares material, stays open: extending an open line by a
search is left until its cost is measured.

## 5. The packet (MS)

| # | What | From |
| --- | --- | --- |
| MS1 | A mechanism's `reads` requested on the whole scan at once; `max_rounds` stays 3 | §3.3 |
| MS2 | One relation served once: a board item and the claim of the same relation (`removed_defender_v2`/`lost_defence`, `fork_v2`/double attack, `newly_exposed_v1`/exposed, `discovery_v2`/attack) become one item; the claim's part is the link "explains that consequence" | §2.3 |
| MS3 | A relation's time: **began** (today's board), **holds** (stood before and after: `left_en_prise_v2`'s piece; the setting the agent built itself), **ended** (a lost defence) | §2.3, §2.4 |
| MS4 | The three groups of §2.3 as one meaning each with its variant and evidence ("a better move" by judgement / by consequence / by margin; "offers material"; "allows a mate"); every claim and label rule stays, the digest shows one | §2.3 |
| MS5 | `sacrifice_compensated_v1` decides a mate against an open keeping line by its score | §4 |
| MS6 | The default digest smaller, nothing deleted: `lines.others` and `refuted` behind `detail` (counts stay), `findings` replaced by `proves` where a claim has one, and the simplification agreed after AG8 (cite by handle; `part` in place of `use`; `proves` in place of `text`/`says`) — as far as §7 Q3 settles | §2.1, §2.2 |
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
3. **The simplification agreed after AG8** (MS6): all of it in MS, or `part` and `proves` now and
   citing by handle later? Recommended: all — MS changes the same records and the same guide.
4. **The groups of §2.3** (MS4): one claim with variants (fewer templates; the label rules read the
   variant), or the templates kept with the digest showing the strongest one? Recommended: kept,
   shown once — no label rule or cached analysis changes.

## 8. The evidence

Scripts and outputs of this note (session scratchpad, not in the repository): `measure.py`
(§2), `probe_eager.py` and `probe_famcost.py` (§3.1), `probe_rounds4.py` and `probe_trace21.py`
(§3.2), `probe_batch.py` (§3.3), `probe_sac.py` and `probe_sac_all.py` (§4).
