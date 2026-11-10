# harness_v5 (TB-D §3; harness rev. 9): the runner's messages to the agent in arm H — harness_v4's,
# with a conversation per moment (story), compaction (compact, notes, notes_long) and the answer cap

## task
이 대국은 Calliope에 이미 열려 있어. 게임 id는 {game_id}야. open_game을 다시 부르지 마. 고정 장면 {moments}을 한 장면씩 해설할 거야. 장면마다 대화를 새로 시작하고, 내가 단계를 알려 줄게. 단계 지시를 따르고, 제출하라는 지시가 있기 전에는 submit_commentary를 부르지 마.

## facts
[{move} — 사실과 결정적 원인] 도구로 이 장면의 사실을 모아서 근거(ref)와 함께 최대 여덟 개로 써. 수순의 결과는 직접 세지 말고 도구가 계산한 값을 읽어: explore의 ledger(누가 무엇을 잡았는지, 편별 순득실, 끝 위치, 끝 평가가 누구에게 유리한지), compare_lines의 candidates와 ranking(두는 쪽 기준으로 어느 수가 나은지), squares(한 칸의 공격자와 수비자 전부, 수가 무엇을 바꿨는지). 엔진 수순을 옮겨 적는 대신 explore의 continue_with: "engine"을 써. 둔 수와 최선 수의 수순과 평가는 분석 기록의 것(analysis_score, source: "analysis")을 인용해. source가 "search"인 수순이나 평가는 별도 탐색의 것이야: 문장에 쓸 때는 "별도 탐색에서는"처럼 그 출처를 밝혀. ledger의 net은 라인 시작 대비 얻거나 잃은 양이지 누가 앞섰는지가 아니야: 누가 앞서는지는 standing을 읽어. 문장에서는 수순의 물질을 "흑이 4점을 잃는다"처럼 얻고 잃은 양으로 쓰고, 누가 앞서는지는 standing대로 "흑이 1점 앞선다"처럼 써. 그다음 이 수가 그 판정을 받은 결정적 원인 하나를 사슬로 써: 그 수 → 상대의 구체적인 응수나 수순 → 결과(기물 몇 점을 얻거나 잃음, 체크메이트, 또는 아무것도 얻지 못함). 보조 원인은 최대 둘.
마지막에 결정적 원인이 기대는 주장을 JSON 블록 하나로 적어. 종류는 여섯 가지야:
```json
{{"claims": [
  {{"kind": "line_net", "ref": "x…", "side": "white|black", "value": 0}},
  {{"kind": "line_capture", "ref": "x…", "by": "white|black", "piece": "rook", "square": "f6"}},
  {{"kind": "piece_at_end", "ref": "x…", "side": "white|black", "piece": "bishop", "square": "d6"}},
  {{"kind": "defenders", "ref": "f…", "square": "f7", "value": ["Kg8", "Nd6"]}},
  {{"kind": "better_for_mover", "ref": "k…", "move": "Qe1", "than": "Qxe3"}},
  {{"kind": "score", "ref": "s…", "favours": "white|black|neither"}}
]}}
```
수순의 기물 득실, 잡기, 끝 위치, 수비·공격 관계(defenders 또는 attackers), 두 수의 비교, 평가가 누구에게 유리한지를 원인에 쓰면 그 주장마다 이 블록에 하나씩 넣어. ref는 그 값을 담은 도구 결과의 ref야(squares는 refs.pieces). 아직 제출하지 마.

## retry
[{move} — 판정: 통과하지 못함] 이유: {problems}
필요하면 도구로 사실을 더 확인하고, 사실과 결정적 원인과 주장 블록을 다시 써.

## check
[{move} — 주장 확인: 기록과 다름] {problems}
해당 도구를 다시 불러 그 기록대로 고쳐. 고친 주장마다 그 기록의 ref를 달아. 그다음 사실과 결정적 원인과 주장 블록을 다시 써.

## submit
[{move} — 제출] 판정을 {how}. 이 장면의 해설을 submit_commentary로 제출해. 결정적 원인을 먼저 쓰고, 가이드의 형식을 따라. 문장은 확인된 주장과 어긋나지 않게 써. 거부되면 고쳐서 다시 제출해.

## passed
통과했어

## exhausted
세 번 통과하지 못했지만 시도 한도에 닿았어

## gate
지금은 제출할 수 없어. 제출은 이 장면의 제출 단계에서, 이 장면(ply {ply})만 할 수 있어. 지금 단계의 지시를 따라 줘.

## unsubmitted
[{move} — 제출 안 됨] 이 장면(ply {ply})의 해설이 아직 받아들여지지 않았어. submit_commentary를 불러서 이 장면을 제출해. 거부되면 표시된 문제를 고쳐서 다시 제출해.

## held
[제출 보류: 문장의 틀] 다음 문장이 인용한 기록과 다른 틀로 숫자를 썼어: {problems}
그 문장을 기록이 말하는 대로 고치거나 빼고 다시 제출해.

## story
[지금까지의 해설] 앞 장면에서 받아들여진 해설이야. 이어지는 이야기로 쓰되, 이 내용을 되풀이하지 말고 인용 근거로 쓰지 마. 인용할 근거는 이 장면에서 도구로 다시 받아.
{story}

## compact
[대화 정리] 이 장면의 대화가 길어져서 곧 새로 시작할 거야. 해설에 필요한 것만 노트로 남겨: 수, 주장, 그 근거의 ref. 2,000토큰 이내로, 노트만 써. 도구는 부르지 마.

## notes_long
노트가 너무 길어. 더 줄여서 노트만 다시 써.

## notes
[이 장면의 노트] 대화를 새로 시작했어. 앞에서 남긴 노트야:
{notes}

## passed_facts
[판정을 통과한 사실 답]
{facts}

## refused_detail
[{tool} 답이 너무 큼: {size}바이트] 탐색한 라인 전체는 보내지 않아. 그 라인의 끝 위치(from_root)에서 facts나 squares로 필요한 것만 물어봐.

## refused_length
[{tool} 답이 너무 큼: {size}바이트] length를 줄이거나 후보 수를 줄여서 다시 불러.

## refused_overview
[{tool} 답이 너무 큼: {size}바이트] plies 범위를 좁혀서 다시 불러.

## refused_facts
[{tool} 답이 너무 큼: {size}바이트] families를 줄이거나 위치를 좁혀서 다시 불러.

## refused_other
[{tool} 답이 너무 큼: {size}바이트] 더 좁은 ref나 범위로 다시 불러.
