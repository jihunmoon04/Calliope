"""Independent pre-implementation E01-E15 + v0.3 serialization contract checker.

Does not import Calliope scenario/selector code and cannot overwrite golden data.

python docs/legacy/corpus/check_observation_bridge_i2i3.py --schema-only
python docs/legacy/corpus/check_observation_bridge_i2i3.py --full  # requires python-chess
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
EXCHANGE = ROOT / "tests/golden/scenario_explanation_cases.json"
CORPUS = HERE / "observation-bridge-i2i3-v1.json"
PUBLIC = HERE / "observation-bridge-i3-dto-golden.json"
CLOSED = {
    "CAPTURE_NORMAL", "CAPTURE_EP", "PROMOTION", "MOVE", "CASTLING_ROOK",
    "FOCUS_LOSSES", "MATERIAL_COUNTS", "EXCHANGE_OBS_CHANGE",
}
UCI = re.compile(r"[a-h][1-8][a-h][1-8][qrbn]?\Z")
# Independent, frozen ordinal snapshots of the source domain enum declarations.
# The same-tier ordering MUST never fall back to lexicographic candidate keys.
FACT_KIND_ORDER = (
    "PIECE_STATE", "FOCUS_OCCUPANT", "FOCUS_ATTACKERS",
    "FOCUS_LEGAL_CAPTURES_NOW", "PAWN_FLAGS", "PAWN_SUPPORTERS",
    "FILE_STATE", "ATTACK_FOOTPRINT", "ATTACK_PARTITION",
    "RAY_STATE", "PIN_PRESENT",
)
EVENT_KIND_ORDER = ("CAPTURE", "PROMOTION", "MOVE", "CASTLING_ROOK")
COUNT_KIND_ORDER = ("MATERIAL_COUNTS", "FOCUS_LOSSES")
PIECE_TYPE_ORDER = ("pawn", "knight", "bishop", "rook", "queen", "king")


def _board_square_index(square):
    must(re.fullmatch(r"[a-h][1-8]", square) is not None,
         "noncanonical square in typed candidate key")
    return (int(square[1]) - 1) * 8 + ord(square[0]) - ord("a")


def _typed_candidate_tie(key):
    """Source enum declaration order, then physical board order; never str(key).

    A one-ply focus SquareKey has ordinal FOCUS_OCCUPANT before FOCUS_ATTACKERS,
    even though a lexicographic sort does the reverse. Unknown shapes fail closed.
    """
    bucket, rest = key.split("/", 1)
    family, encoded = rest.split(":", 1)
    if bucket in ("STEPS", "ENDPOINTS"):
        must(family in FACT_KIND_ORDER, "unknown fact family " + family)
        family_order = FACT_KIND_ORDER.index(family)
        if encoded.startswith("square-"):
            square = encoded[len("square-"):].split(";", 1)[0]
            return (0, family_order, _board_square_index(square), 0)
        if encoded.startswith("file-"):
            letter = encoded[len("file-"):]
            must(len(letter) == 1 and letter in "abcdefgh", "bad file key")
            return (0, family_order, ord(letter) - ord("a"), 0)
        if encoded.startswith("base-"):
            square = encoded[len("base-"):].split(";", 1)[0]
            return (0, family_order, _board_square_index(square), 0)
        raise AssertionError("unsupported typed property identity " + key)
    if bucket == "EVENTS":
        must(family in EVENT_KIND_ORDER, "unknown event family " + family)
        parts = encoded.split(":")
        must(re.fullmatch(r"ply[1-9][0-9]*", parts[0]) is not None, "bad event ply")
        if len(parts) == 2 and parts[1] == "capture":
            return (1, EVENT_KIND_ORDER.index(family), 0, 0)
        must(len(parts) == 2 and parts[1].startswith("base-"), "bad transition")
        return (1, EVENT_KIND_ORDER.index(family),
                _board_square_index(parts[1][len("base-"):]), 0)
    if bucket == "AGGREGATES":
        must(family in COUNT_KIND_ORDER, "unknown count family " + family)
        color, piece = encoded.split(":")
        must(color in ("white", "black") and piece in PIECE_TYPE_ORDER, "bad count key")
        return (2, COUNT_KIND_ORDER.index(family),
                0 if color == "white" else 1, PIECE_TYPE_ORDER.index(piece))
    raise AssertionError("unsupported candidate bucket " + bucket)


def check_e08_tie_regression():
    """E08 changes both focus families at the same ply/tier.

    Typed FactKind order gives FOCUS_OCCUPANT priority over FOCUS_ATTACKERS.
    """
    occupant = "STEPS/FOCUS_OCCUPANT:square-e4;ply=1"
    attackers = "STEPS/FOCUS_ATTACKERS:square-e4;ply=1"
    must(_typed_candidate_tie(occupant) < _typed_candidate_tie(attackers),
         "E08 focus tie regressed to lexicographic ordering")


SOURCES = {
    "CAPTURE": ("step", 0), "TRANSITION": ("step", 4),
    "MATERIAL": ("endpoints", 2), "PIECE_HISTORY": ("frame", 3),
    "SQUARE_ACCESS": ("frame", 1), "PAWN_STRUCTURE": ("frame", 3),
    "FILE_STRUCTURE": ("frame", 1), "PIECE_ACTIVITY": ("frame", 3),
    "SLIDER_RAY": ("frame", 5), "ABSOLUTE_PIN": ("frame", 9),
}


def must(ok, reason):
    if not ok:
        raise AssertionError(reason)


def load():
    return (
        json.loads(CORPUS.read_text(encoding="utf-8")),
        json.loads(EXCHANGE.read_text(encoding="utf-8")),
        json.loads(PUBLIC.read_text(encoding="utf-8")),
    )


def check_schema(doc, old):
    must(doc["version"] == "calliope.observation_bridge_joint_design_v1", "wrong corpus version")
    must(old["version"] == "scenario_explanation_corpus_v2", "wrong source corpus")
    cs = doc["constraints"]
    must(cs["max_public_exchange_lines"] == 2 and cs["max_public_plies_per_line"] == 8, "public line cap")
    must(cs["max_observation_sentences_per_section"] == 2 and cs["max_observation_sentences_per_request"] == 6, "sentence cap")
    must(cs["legacy_exchange_bytes_unchanged"] is True and cs["dependency_closed_selection"] is True, "missing invariants")
    orig = {c["id"]: c for c in old["cases"]}
    expected = [f"E{i:02}" for i in range(1, 16)]
    must([x["id"] for x in doc["cases"]] == expected, "missing/duplicated E01-E15")
    for c in doc["cases"]:
        ident=c["id"]
        legacy=orig[ident]
        must(all(c[k] == legacy[k] for k in ("fen","focus")), ident+": changed root/focus")
        must(c["moves"] == legacy["moves"], ident+": changed line")
        must(c["expected_focus_capture_count"] == sum(x["landing"] == c["focus"] for x in legacy["captures"]), ident+": focus count")
        must(c["expected_status"] == legacy["summary_expectations"]["status"], ident+": status")
        must(c["request_origin"] == "USER" and c["cap"] == 2, ident+": budget/origin")
        selected=c["selected"]
        must(len(selected) <= 2 and len(selected) == len({x["key"] for x in selected}), ident+": repeated/capped keys")
        must(c["selected_source_kind"] == [x["source_kind"] for x in selected], ident+": source kinds")
        must(all(x["template_id"] in CLOSED and x["text"].startswith("In the supplied line") and x["text"].endswith(".") for x in selected), ident+": unknown template/grammar")
        must(not set(x["key"] for x in selected) & set(c["candidate_cap_exclusions"]), ident+": selection and cap exclusion")
        must(not set(x["key"] for x in selected) & set(c["candidate_context_only"]), ident+": selection and context exclusion")
        must(all(UCI.fullmatch(x) is not None for x in c["moves"]), ident+": malformed UCI")
        for item in c.get("candidate_semantic_duplicates",[]):
            must(item["key"].startswith("ENDPOINTS/") and item["duplicate_of"].startswith("STEPS/"), ident+": reverse dedup")
            must(item["key"].removeprefix("ENDPOINTS/") == item["duplicate_of"].removeprefix("STEPS/").split(";ply=")[0], ident+": wrong duplicate")
        if ident == "E01": must(not selected and not c["moves"], "E01 not empty")
        if ident == "E08":
            must([x["key"] for x in selected] == [
                "EVENTS/CAPTURE:ply1:capture",
                "STEPS/FOCUS_OCCUPANT:square-e4;ply=1",
            ], "E08 immutable capture+occupant expectation changed")
            must(_typed_candidate_tie("STEPS/FOCUS_OCCUPANT:square-e4;ply=1") <
                 _typed_candidate_tie("STEPS/FOCUS_ATTACKERS:square-e4;ply=1"),
                 "E08 typed FactKind precedence changed")


def valid_public_id(value):
    must(isinstance(value,str), "nonstring observation ID")
    parts=value.split("/")
    must(len(parts)==5 and parts[0]=="obs.v1" and re.fullmatch(r"p|x[0-9]+",parts[1]), "wrong observation_id grammar")
    must(parts[2] in ("steps","endpoints","events","aggregates"), "wrong ID bucket")
    must(re.fullmatch(r"[A-Z_]+",parts[3]) is not None, "wrong family")
    must(re.fullmatch(r"[a-z]+=[a-z0-9,;\-=]+",parts[4]) is not None, "wrong key encoding")
    return parts


def check_public_schema(dto):
    must(dto["contract_version"] == "observation_public_dto_v1", "wrong public golden")
    data=dto["result"]
    must(set(data)=={"schema_version","base_result","played","exchange_lines"}, "wrong top-level v0.3 DTO keys")
    must(data["schema_version"]=="0.3" and data["base_result"]["schema_version"]=="0.2", "wrong nested schema")
    root= dto["source_position_fen"]
    after=dto["after_position_fen"]
    pid=lambda fen:"pos_"+sha256(fen.encode("utf-8")).hexdigest()[:24]
    must(dto["source_anchor_initial"]==pid(root) and dto["source_anchor_after"]==pid(after), "fake position-id hash")
    base=data["base_result"]
    must(set(base)=={"schema_version","position_fen","judgement","claims","selected_claim_ids","variations","commentary","metadata"}, "legacy DTO fields")
    must(base["position_fen"]==root and base["metadata"]["position_id"]==pid(root), "legacy identity")
    must(base["judgement"]["move_uci"]=="e4d5" and base["claims"]==[] and base["commentary"] is None, "synthetic legacy payload")
    must(set(base["judgement"])=={"move_uci","best_move_uci","quality","rank","cp_loss","expected_score_loss","forcedness"}, "judgement fields")
    must(set(base["metadata"])=={"position_id","engine","analysis","forcedness","explanation"}, "metadata fields")
    scopes={"played_transition":"p","supplied_line_exchange":"x0"}
    sections=[data["played"],*data["exchange_lines"]]
    must(len(sections)==2 and len(sections[0]["sentences"])==2 and len(sections[1]["sentences"])==2, "public example section count")
    all_ids=[]
    for i,sec in enumerate(sections):
        must(set(sec)=={"label","scope","supplied_line_uci","focus_square","status","focus_capture_count","sentences"}, "section field drift")
        expected_scope="played_transition" if i==0 else "supplied_line_exchange"
        must(sec["scope"]==expected_scope, "wrong scope")
        must(sec["label"]==("Observed facts after the played move" if i==0 else "Facts in the supplied line"), "label")
        must(sec["supplied_line_uci"]==["e4d5"], "line binding")
        must(sec["focus_square"]==(None if i==0 else "d5"), "focus")
        must(sec["status"]==(None if i==0 else "FOCUS_CAPTURES_OBSERVED"), "status")
        must(sec["focus_capture_count"]==(None if i==0 else 1), "count")
        for sent in sec["sentences"]:
            must(set(sent)=={"observation_id","template_id","text","source_refs"}, "sentence keys")
            parts=valid_public_id(sent["observation_id"])
            must(parts[1] == scopes[sec["scope"]], "section-scoped ID")
            must(len(sent["source_refs"])>0 and isinstance(sent["text"],str) and sent["text"].endswith("."), "missing provenance/text")
            must(sent["template_id"] in CLOSED|{"PLAYED_CHANGE"}, "unknown template ID")
            all_ids.append(sent["observation_id"])
            for ref in sent["source_refs"]:
                must(set(ref)=={"kind","anchor_kind","index","position_ids","selectors"}, "ref DTO drift")
                must(ref["kind"] in SOURCES, "unrecognized SourceKind")
                anchor,n=SOURCES[ref["kind"]]
                must(ref["anchor_kind"]==anchor and len(ref["selectors"])==n, "selector cardinality")
                must(type(ref["index"]) is int if anchor in ("step","frame") else ref["index"] is None, "index type")
                must(ref["position_ids"]==([pid(root),pid(after)] if anchor in ("step","endpoints") else [pid(root) if ref["index"]==0 else pid(after)]), "position anchors")
                must(all(isinstance(x,str) for x in ref["selectors"]), "typed ref tokens")
    must(len(all_ids)==len(set(all_ids)), "duplicate observation ids")
    must(all_ids == [
        "obs.v1/p/events/CAPTURE/ply=1",
        "obs.v1/p/steps/FILE_STATE/ply=1;file=d",
        "obs.v1/x0/events/CAPTURE/ply=1",
        "obs.v1/x0/aggregates/FOCUS_LOSSES/color=black;piece=pawn",
    ], "exact independently frozen public observation-id golden changed")
    # This is a deterministic synthetic adapter stub, never real Stockfish truth.
    must(dto["fixture_kind"]=="synthetic_legacy_dto_factual_observation", "missing synthetic label")
    def canonical(x):
        return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    must(canonical(json.loads(canonical(data)))==canonical(data), "serialization instability")
    must(sections[0]["sentences"][0]["source_refs"] == sections[1]["sentences"][0]["source_refs"], "shared capture source mismatch")
    must(sections[1]["sentences"][1]["source_refs"] == sections[1]["sentences"][0]["source_refs"], "focus loss witness mismatch")
    return 4


def check_full(doc, dto):
    try:
        import chess
    except ModuleNotFoundError as ex:
        raise RuntimeError("Full mode requires python-chess") from ex

    all_count=0
    for case in doc["cases"]:
        ident=case["id"]; board=chess.Board(case["fen"])
        must(board.is_valid(), ident+": bad FEN")
        initial=board.copy()
        maps={square:square for square in board.piece_map()}
        frames=[board.copy()]
        phys=[dict(maps)]
        captures={}
        promos={}
        promoted_by_base=defaultdict(list)
        counts=Counter()
        count_causes=defaultdict(set)
        move_events={}
        for ply, raw in enumerate(case["moves"],1):
            move=chess.Move.from_uci(raw)
            must(move in board.legal_moves, ident+": illegal move "+raw)
            pre=board.copy(); source=move.from_square; target=move.to_square
            base=maps.get(source)
            must(base is not None, ident+": no physical source")
            was_capture=pre.is_capture(move)
            victim_sq=target+(-8 if board.turn else 8) if pre.is_en_passant(move) else target
            if was_capture:
                victim=pre.piece_at(victim_sq)
                must(victim is not None, ident+": missing victim")
                victim_base=maps.pop(victim_sq)
                mover=pre.piece_at(source)
                must(mover is not None, ident+": missing mover")
                prefix=f"In the supplied line, at ply {ply}, "
                if pre.is_en_passant(move):
                    text=(prefix+f"{'white' if mover.color else 'black'} {chess.piece_name(mover.piece_type)} on {chess.square_name(source)} captures en passant, landing on {chess.square_name(target)} and removing {'white' if victim.color else 'black'} {chess.piece_name(victim.piece_type)} on {chess.square_name(victim_sq)} from {chess.square_name(victim_sq)}.")
                    template="CAPTURE_EP"
                else:
                    text=(prefix+f"{'white' if mover.color else 'black'} {chess.piece_name(mover.piece_type)} on {chess.square_name(source)} captures {'white' if victim.color else 'black'} {chess.piece_name(victim.piece_type)} on {chess.square_name(target)}.")
                    template="CAPTURE_NORMAL"
                key=f"EVENTS/CAPTURE:ply{ply}:capture"
                deps=tuple(promoted_by_base[victim_base])
                captures[key]={"template_id":template,"text":text,"landing":chess.square_name(target),"victim_square":chess.square_name(victim_sq),"victim_color":"white" if victim.color else "black","victim_type":chess.piece_name(victim.piece_type),"ply":ply,"prereq":deps}
                count_causes[f"AGGREGATES/MATERIAL_COUNTS:{captures[key]['victim_color']}:{captures[key]['victim_type']}"].add(key)
                if chess.square_name(target)==case["focus"]:
                    counts[(captures[key]["victim_color"],captures[key]["victim_type"])]+=1
            if pre.is_castling(move):
                kside=chess.square_file(target)==6
                rook_source=(chess.H1 if pre.turn else chess.H8) if kside else (chess.A1 if pre.turn else chess.A8)
                rook_target=(chess.F1 if pre.turn else chess.F8) if kside else (chess.D1 if pre.turn else chess.D8)
                rook_base=maps.pop(rook_source)
                maps[rook_target]=rook_base
            maps[target]=maps.pop(source)
            if move.promotion:
                event_key=f"EVENTS/PROMOTION:ply{ply}:base-{chess.square_name(base)}"
                promos[event_key]={"template_id":"PROMOTION","text":f"In the supplied line, at ply {ply}, the piece initially on {chess.square_name(base)} moves from {chess.square_name(source)} to {chess.square_name(target)} and promotes to {chess.piece_name(move.promotion)}.","ply":ply}
                promoted_by_base[base].append(event_key)
                color="white" if pre.turn else "black"
                count_causes[f"AGGREGATES/MATERIAL_COUNTS:{color}:pawn"].add(event_key)
                count_causes[f"AGGREGATES/MATERIAL_COUNTS:{color}:{chess.piece_name(move.promotion)}"].add(event_key)
            board.push(move)
            frames.append(board.copy());phys.append(dict(maps))
        must(board.is_valid(), ident+": invalid final position")
        focus_count=sum(counts.values())
        must(focus_count==case["expected_focus_capture_count"], ident+": focus-count mismatch")
        status="FOCUS_CAPTURES_OBSERVED" if focus_count else "NO_FOCUS_CAPTURE"
        must(status==case["expected_status"], ident+": focus status mismatch")
        related_capture=any(e["landing"]==case["focus"] or e["victim_square"]==case["focus"] for e in captures.values())
        # Source independent early-rank candidates, plus the relevant focus
        # changes for E08/E10/E11. Other property families cannot outrank
        # a focus change in these real fixtures due canonical FactKind order.
        ranks={}
        for key,e in captures.items():
            tier=0 if e["landing"]==case["focus"] else 1 if e["victim_square"]==case["focus"] else (7 if related_capture else 4.5)
            ranks[key]=(tier,e["ply"],key,e["template_id"],e["text"],tuple(e["prereq"]))
        for key,e in promos.items():
            ranks[key]=(2,e["ply"],key,e["template_id"],e["text"],())
        for (color,kind),num in counts.items():
            k=f"AGGREGATES/FOCUS_LOSSES:{color}:{kind}"
            witness=tuple(k0 for k0,e in captures.items() if e["landing"]==case["focus"] and e["victim_color"]==color and e["victim_type"]==kind)
            txt=f"In the supplied line, captures landing on {case['focus']} remove {num} {color} {kind} piece(s)."
            ranks[k]=(3,0,k,"FOCUS_LOSSES",txt,witness)
        context_only=set(case["candidate_context_only"])
        for color,colorv in (("white",chess.WHITE),("black",chess.BLACK)):
            for name,kind in (("pawn",chess.PAWN),("knight",chess.KNIGHT),("bishop",chess.BISHOP),("rook",chess.ROOK),("queen",chess.QUEEN)):
                amount=len(board.pieces(kind,colorv))-len(initial.pieces(kind,colorv))
                if amount:
                    key=f"AGGREGATES/MATERIAL_COUNTS:{color}:{name}"
                    if not related_capture:
                        context_only.add(key)
                    else:
                        txt=f"In the supplied line, at the supplied endpoint, the {color} {name} count changes by {amount:+d} relative to the initial frame."
                        ranks[key]=(4,0,key,"MATERIAL_COUNTS",txt,tuple(count_causes[key]))
        def focus_value(b,m,family):
            sq=chess.parse_square(case["focus"])
            if family=="FOCUS_OCCUPANT":
                piece=b.piece_at(sq)
                if piece is None: return "empty"
                base=m[sq]
                return f"{'white' if piece.color else 'black'} {chess.piece_name(piece.piece_type)} on {case['focus']} (initially {chess.square_name(base)})"
            segments=[]
            for color,name in ((chess.WHITE,"white"),(chess.BLACK,"black")):
                members=[]
                for square in b.attackers(color,sq):
                    piece=b.piece_at(square)
                    assert piece is not None
                    members.append((m[square],f"{name} {chess.piece_name(piece.piece_type)} on {chess.square_name(square)} (initially {chess.square_name(m[square])})"))
                members.sort(key=lambda x:x[0])
                segments.append(name+"=("+", ".join(x[1] for x in members)+")")
            return ", ".join(segments)
        focus_kinds=("FOCUS_OCCUPANT","FOCUS_ATTACKERS")
        before_after={}
        for family in focus_kinds:
            for frame in range(1,len(frames)):
                earlier=focus_value(frames[frame-1],phys[frame-1],family)
                later=focus_value(frames[frame],phys[frame],family)
                if earlier==later:continue
                k=f"STEPS/{family}:square-{case['focus']};ply={frame}"
                txt=f"In the supplied line after ply {frame}, square {case['focus']} [{family}] from frame {frame-1} to {frame}: {earlier} -> {later}."
                ranks[k]=(6,frame,k,"EXCHANGE_OBS_CHANGE",txt,())
            if len(frames)>1:
                earlier=focus_value(frames[0],phys[0],family)
                later=focus_value(frames[-1],phys[-1],family)
                if earlier!=later:
                    k=f"ENDPOINTS/{family}:square-{case['focus']}"
                    if len(frames)==2:
                        before_after[k]=f"STEPS/{family}:square-{case['focus']};ply=1"
                    else:
                        txt=f"In the supplied line after ply {len(frames)-1}, square {case['focus']} [{family}] from frame 0 to {len(frames)-1}: {earlier} -> {later}."
                        ranks[k]=(5,len(frames)-1,k,"EXCHANGE_OBS_CHANGE",txt,())
        all_keys=sorted(ranks,key=lambda k:(ranks[k][0],ranks[k][1],_typed_candidate_tie(k)))
        if ident == "E08":
            # Both values genuinely change in this one-ply line: an occupied
            # square becomes empty and its geometric attacker set changes.
            occ = "STEPS/FOCUS_OCCUPANT:square-e4;ply=1"
            att = "STEPS/FOCUS_ATTACKERS:square-e4;ply=1"
            must(occ in ranks and att in ranks, "E08 simultaneous focus facts missing")
            must(ranks[occ][:2] == ranks[att][:2],
                 "E08 is no longer a same-tier/same-ply regression")
            must(all_keys.index(occ) < all_keys.index(att),
                 "E08 must order FOCUS_OCCUPANT before FOCUS_ATTACKERS")
        selected=[]; reasons={}
        for key in all_keys:
            if key in context_only:
                reasons[key]="CONTEXT_ONLY"
                continue
            if len(selected)>=2:
                reasons[key]="CAP_EXCEEDED"
                continue
            _,_,_,_,_,dependencies=ranks[key]
            # Any capture may pull its promoting witness into the same
            # two-slot presentation; count never pulls its own witnesses.
            if key.startswith("EVENTS/CAPTURE"):
                needed=[r for r in dependencies if r not in selected]
                block=[key,*needed]
                if not all(x in ranks for x in block) or len(block)>2-len(selected):
                    reasons[key]="CAP_EXCEEDED"
                    continue
                for x in block:
                    if x not in selected:
                        selected.append(x)
                        reasons[x]=None
            elif key.startswith("AGGREGATES/"):
                if not all(r in selected for r in dependencies):
                    reasons[key]="CAP_EXCEEDED"
                    continue
                selected.append(key);reasons[key]=None
            else:
                if key not in selected:
                    selected.append(key);reasons[key]=None
        must(len(selected)<=2, ident+": cap overflow")
        expected=[x["key"] for x in case["selected"]]
        must(selected==expected, ident+": independent dependency-aware priority: "+str(selected)+" != "+str(expected))
        for x in case["selected"]:
            k=x["key"]
            data=ranks[k]
            must((data[3],data[4])==(x["template_id"],x["text"]), ident+": exact text/template mismatch "+k)
            actual_kind="CAPTURE" if k.startswith("EVENTS/CAPTURE") or k.startswith("AGGREGATES/FOCUS_LOSSES") else ("TRANSITION" if k.startswith("EVENTS/PROMOTION") else "SQUARE_ACCESS" if "/FOCUS_" in k else "MATERIAL")
            must(actual_kind==x["source_kind"], ident+": source kind "+k)
        for key in case["candidate_cap_exclusions"]:
            must(key in ranks and reasons.get(key)=="CAP_EXCEEDED", ident+": wrong cap exclusion "+key)
        for key in case["candidate_context_only"]:
            must(key in context_only, ident+": wrong context exclusion "+key)
        for row in case.get("candidate_semantic_duplicates",[]):
            k=row["key"]
            must(before_after.get(k)==row["duplicate_of"], ident+": one-ply duplicate wrong")
        all_count+=1
    return all_count


def main():
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--schema-only",action="store_true")
    group.add_argument("--full",action="store_true")
    args=parser.parse_args()
    doc,old,dto=load()
    check_schema(doc,old)
    check_e08_tie_regression()
    n=check_public_schema(dto)
    print(f"SCHEMA PASS: {len(doc['cases'])} EXCHANGE scenarios, {n} complete public DTO example sentences")
    if args.full:
        count=check_full(doc,dto)
        print(f"CHESS PASS: {count} legal EXCHANGE fixtures with independently recomputed dependency-closed top-two")


if __name__=="__main__":
    main()
