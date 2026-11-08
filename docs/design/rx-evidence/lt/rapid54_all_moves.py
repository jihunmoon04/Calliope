import json, os
import chess, chess.engine

r = json.load(open("/mnt/d/00_프로젝트/Calliope/tools/rx/references_v1/train/rapid-54.json", encoding="utf-8"))
print("key causes:")
for c in r.get("key_causes") or []:
    print(" ", json.dumps({k: c.get(k) for k in ("role", "kind", "text", "sentence", "route")}, ensure_ascii=False)[:500])
board = chess.Board(r["fen_before"])
eng = chess.engine.SimpleEngine.popen_uci(os.environ["CALLIOPE_STOCKFISH_PATH"])
rows = []
for move in list(board.legal_moves):
    b = board.copy(); b.push(move)
    if b.is_game_over():
        rows.append((board.san(move), str(b.outcome())))
        continue
    info = eng.analyse(b, chess.engine.Limit(depth=22))
    rows.append((board.san(move), str(info["score"].white())))
eng.quit()
for san, score in sorted(rows, key=lambda x: x[1]):
    print(san, score)
