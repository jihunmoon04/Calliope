"""One model request in a process of its own (RX2-D §2, RX1 review N4).

`python -m tools.rx.request` reads `{"endpoint", "body"}` as JSON from stdin, posts the body with the key
from `OPENROUTER_API_KEY`, and writes one JSON object to stdout: `{"status": 200, "text": ...}`, or
`{"status": <code>, "text": ...}` for an HTTP error, or `{"error": ...}`. Its parent kills it at the
request's deadline, which ends the socket with the process.

HS-D §4 (review N2): a body cut short (`http.client.IncompleteRead`, an `HTTPException`, not an
`OSError`) or a connection dropped mid-answer is `{"error": ..., "kind": "transport"}`, which the
parent retries once; before HS the child died on it with no JSON.
"""

from __future__ import annotations

import http.client
import json
import os
import sys
import urllib.error
import urllib.request

KEY_VAR = "OPENROUTER_API_KEY"


def claude(job: dict) -> dict:
    """TB-D C2: one call on the Claude API through the official SDK (`create` or `count_tokens`),
    with the key from `ANTHROPIC_API_KEY`. The answer is `{"status": 200, "doc": <the answer as a
    dict>}`; an HTTP error `{"status": <code>, "text": ...}`; a connection error or timeout
    `{"error": ..., "kind": "transport"}`."""

    import anthropic

    client = anthropic.Anthropic(max_retries=2, timeout=job.get("attempt_seconds") or 90)
    try:
        if job["call"] == "count_tokens":
            answer = client.messages.count_tokens(**job["body"])
        else:
            answer = client.messages.create(**job["body"])
        return {"status": 200, "doc": answer.to_dict()}
    except anthropic.APIStatusError as error:
        return {"status": error.status_code, "text": str(error.message)[:2000]}
    except (anthropic.APITimeoutError, anthropic.APIConnectionError) as error:
        return {"error": f"{type(error).__name__}: {error}"[:500], "kind": "transport"}


def main() -> int:
    job = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    if job.get("provider") == "claude":
        sys.stdout.write(json.dumps(claude(job), ensure_ascii=False))
        return 0
    request = urllib.request.Request(
        job["endpoint"],
        data=json.dumps(job["body"], ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Bearer " + os.environ.get(KEY_VAR, ""),
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request) as response:  # the parent bounds the time
            out = {"status": response.status, "text": response.read().decode("utf-8", "replace")}
    except urllib.error.HTTPError as error:
        out = {"status": error.code, "text": error.read().decode("utf-8", "replace")[:2000]}
    except (http.client.HTTPException, ConnectionError) as error:  # HS-D §4: cut short mid-answer
        out = {"error": f"{type(error).__name__}: {error}"[:500], "kind": "transport"}
    except (urllib.error.URLError, OSError) as error:
        out = {"error": f"{type(error).__name__}: {getattr(error, 'reason', error)}"}
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
