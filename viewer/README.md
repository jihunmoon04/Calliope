# Calliope viewer

A static page that shows one `calliope_result_v1` document (AR-D): the board, the move list with
grades and labels, an evaluation graph, and each ply's explanation. Hover an underlined part of an
explanation to see what it names on the board, each in its own position (AR-D §4): the piece, the
move, or the line, step by step. Click to pin it; `Esc` releases it.

It is one file, `index.html`, with no dependencies and no network access. It needs no server
and no API: the analysis is done beforehand by `tools/explain_game`.

## Use

```sh
# 1. analyse a game (Stockfish) and write its result document
CALLIOPE_STOCKFISH_PATH=$HOME/opt/stockfish/stockfish PYTHONPATH=. \
  .venv/bin/python -m tools.explain_game game.pgn --json viewer/local/game.json

# 2a. open viewer/index.html in a browser and pick the file (or drop it on the page), or
# 2b. serve the folder and name the file in the URL
python -m http.server 8000 --directory viewer
#    → http://localhost:8000/?file=local/game.json
```

`viewer/local/` is git-ignored, so your own games stay out of the repository. On a remote machine,
forward port 8000, or download `index.html` and the JSON file and open them locally.

Keys: `←` / `→` move through the game (or step through a pinned line), `Home` / `End`, `F` flips
the board, `Esc` closes a preview.

## Tests

`tests/viewer/test_viewer.py` runs the page's pure part under `node` (skipped without it). It
checks the following:
- the moves it plays (castling, en passant, promotion) against python-chess;
- every analysed ply's position against the document's FENs;
- the frames of the fork and better-move segments.
