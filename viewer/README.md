# Calliope viewer

A static page that shows one `calliope_result_v1` document (AR-D): the board, the move list with
grades and labels, an evaluation graph, and each ply's explanation. Hover an underlined part of an
explanation to see what it names on the board, each in its own position (AR-D §4): the piece, the
move, or the line, step by step. Click to pin it; `Esc` releases it.

It is one file, `index.html`, with no dependencies and no network access. It needs no server
and no API: the analysis is done beforehand by `tools/explain_game`.

## With the analysis server (AS-D, AS2)

```sh
CALLIOPE_STOCKFISH_PATH=$HOME/opt/stockfish/stockfish PYTHONPATH=. \
  .venv/bin/python -m tools.serve --port 8765
```

The server serves this page at its root. With the API there, the page opens on an **analyse
panel**: paste a PGN (or pick a `.pgn` file), optionally a ply range, and start. The page then
shows the progress (plies done, the current move, the time left) by polling every 2 s, and the
result when it is done. `?game=<id>` reopens a job; earlier games are listed on the panel.

Every URL the page uses is relative, so it works under a proxy's prefix: open code-server's
`/proxy/8765/` (a path without the trailing `/` is corrected by the page itself).

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

A page can also carry its document: a
`<script type="application/json" id="calliope-doc">…</script>` placed before the page's script is
loaded at start, so one HTML file can be shared without a JSON file beside it (escape `</` in the
JSON as `<\/`). On a phone the layout is one column, with the explanation right under the board.

Keys: `←` / `→` move through the game (or step through a pinned line), `Home` / `End`, `F` flips
the board, `Esc` closes a preview.

## AI commentary (AG3a, AG3b)

Under the ply panel, an **AI commentary** panel shows the agent's commentary of the ply, with its
propositions previewed on the board by hover and pin. It reads `ai_commentary` from a document
(`tools/explain_game --json --with-commentary DATA`) or, against the server, the commentary route,
fetched after the result and on 「해설 새로고침」.

Served by `tools/mcp`, the same page is the MCP App behind the agent's `show_game` tool
(`ui://calliope/viewer.html`): it talks to the host instead of the HTTP API, and 「해설 새로고침」
calls `show_game` again.

## Tests

`tests/viewer/test_viewer.py` runs the page's pure part under `node` (skipped without it). It
checks the following:
- the moves it plays (castling, en passant, promotion) against python-chess;
- every analysed ply's position against the document's FENs;
- the frames of the fork and better-move segments.
