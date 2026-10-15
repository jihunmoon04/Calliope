"""AG3-D §5 (App): the viewer as an MCP App under node — the handshake, tool results, the host's
theme, sizes, teardown, unknown requests and the refresh through `show_game` — against documents
that `show_game` answered on the synthetic engine before and after a new commentary."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for sub in ("tests/agent", "tests/server", "tests/facts/search", ""):
    if str(ROOT / sub) not in sys.path:
        sys.path.insert(0, str(ROOT / sub))

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
PLY = 2


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    from agent_helpers import GAME, session

    data = tmp_path_factory.mktemp("app")
    s = session(data)
    try:
        s.open_game(pgn=GAME, plies="1-3")
        before, _ = s.show_game("g1")
        j = s.ply("g1", PLY)["analysis"]["judgements"][0]
        proposition = {"id": "p1", "kind": "judgement", "judgement": j["ref"], "move": "d5",
                       "grade": j["grade"], "label": j["label"],
                       "best_move": j["best"]["move"]["uci"]}  # fmt: skip
        answer = s.submit_commentary("g1", ply=PLY, agent={"name": "t"}, propositions=[proposition],
                                     sentences=[{"text": "1...d5로 받았다.", "class": "sourced",
                                                 "cites": ["p1"]}])  # fmt: skip
        assert answer["accepted"], answer
        after, _ = s.show_game("g1")
    finally:
        s.close()
    path = data / "cases.json"
    path.write_text(json.dumps({"before": before, "after": after, "ply": PLY}))
    run = subprocess.run([NODE, str(ROOT / "tests/viewer/check_app.js"), str(ROOT / "viewer/index.html"),
                          str(path)], capture_output=True, text=True, check=False)  # fmt: skip
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout) | {"id": answer["id"]}


def test_the_handshake_and_the_hosts_context(out) -> None:
    assert out["initialize"] == {
        "jsonrpc": "2.0", "id": 1, "method": "ui/initialize",
        "params": {"protocolVersion": "2026-01-26",
                   "appInfo": {"name": "calliope-viewer", "version": out["version"][1]},
                   "appCapabilities": {"availableDisplayModes": ["inline", "fullscreen"]}},
    }  # fmt: skip
    assert out["beforeReply"] == ["ui/initialize"]  # initialized only after the result
    assert out["afterReply"] == ["ui/initialize", "ui/notifications/initialized"]
    dark = {"theme": "dark", "containerDimensions": {"width": 400, "maxHeight": 600}}
    assert out["contexts"] == [dark]
    assert out["changed"] == ["context", {"theme": "light",
                                          "containerDimensions": {"width": 400, "maxHeight": 600}}]  # fmt: skip
    assert out["version"][0] == "2026-01-26"


def test_sizes_are_sent_debounced_and_only_for_a_flexible_container(out) -> None:
    assert out["debounce"] == [100]
    assert out["firstSize"] == {"jsonrpc": "2.0", "method": "ui/notifications/size-changed",
                                "params": {"width": 400, "height": 900}}  # fmt: skip
    assert out["sizes"] == [{"width": 400, "height": 900}, {"width": 400, "height": 1200}]
    assert out["fixed"] == ["ui/initialize", "ui/notifications/initialized"]


def test_other_sources_partial_input_and_unknown_messages(out) -> None:
    assert out["ignored"] == [0, 0, False]
    ping, unknown = out["requests"]
    assert ping == {"jsonrpc": "2.0", "id": 41, "result": {}}
    assert unknown["id"] == "x7" and unknown["error"]["code"] == -32601


def test_tool_results(out) -> None:
    document, text, cancelled = out["results"]
    assert document == ["document", [1, 2, 3], False, None]  # the result loads as a file does
    assert text == ["text", "다른 도구의 <b>답</b>"]  # shown as text (the page escapes it)
    assert cancelled == ["text", "취소되었습니다"]
    assert out["initError"] == ["no apps here", ["ui/initialize"]]


def test_refresh_calls_show_game_with_the_kept_arguments(out) -> None:
    assert out["noArguments"] == [False, False, False]
    assert out["arguments"] == [False, False, False, False, False, True]
    call = out["call"]
    assert call["method"] == "tools/call"
    assert call["params"] == {"name": "show_game", "arguments": {"game": "g1", "plies": "15-20"}}
    assert out["whilePending"] == [False, True, False, 1]  # a second click sends nothing
    assert out["refreshed"] == [["state", False], ["document", [1, 2, 3], True, PLY],
                                ["state", True]]  # fmt: skip
    assert out["kept"] == [PLY, 1, 1, 0]
    assert out["onPly"] == [False, out["id"]]  # the new commentary, on the ply on screen


@pytest.mark.parametrize("order", ["notificationFirst", "responseFirst"])
def test_a_refresh_result_arriving_twice_keeps_the_ply(out, order) -> None:
    """Review B1: the call's result as a `tool-result` notification and as the JSON-RPC response,
    in either order, is shown once and on the ply on screen; a late duplicate changes nothing."""

    documents, ply, can_refresh = out[order]
    assert documents == [["document", [1, 2, 3], True, PLY]]
    assert ply == 3 and can_refresh is True


def test_a_new_document_of_the_model_starts_on_its_first_ply(out) -> None:
    documents, ply = out["modelCall"]
    assert documents == [["document", [1, 2, 3], False, None], ["document", [1, 2, 3], False, PLY]]
    assert ply == 1


def test_refresh_errors_keep_the_document(out) -> None:
    assert out["errors"] == [["state", False], ["error", "캐시된 수가 없습니다"], ["state", True],
                             ["state", False], ["error", "host failed"], ["state", True]]  # fmt: skip
    assert out["afterErrors"] is True


def test_teardown(out) -> None:
    assert out["teardownAnswer"] == {"jsonrpc": "2.0", "id": 99, "result": {}}
    assert out["teardownState"] == [True, 0, True, False]
    assert out["afterTeardown"] == [0, False, []]  # nothing sent, nothing shown after it
    assert out["pendingSettled"] == "dropped"


def test_the_text_of_a_tool_result(out) -> None:
    assert out["toolText"] == "a\nb"


def test_the_app_page_starts_the_bridge() -> None:
    pytest.importorskip("mcp", reason="the MCP SDK is the optional group `agent`")
    from calliope.agent.server import APP_MARKER, app_page
    from tools.mcp.__main__ import VIEWER

    page = app_page(VIEWER)
    assert page is not None and APP_MARKER in page
    assert 'document.getElementById("calliope-app")' in page and "startApp()" in page
