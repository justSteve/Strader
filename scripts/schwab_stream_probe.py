#!/usr/bin/env python3
"""Account-stream coexistence probe — Steve runs it, TOS open and watched. [st-8bls]

The question st-8bls is gated on: does a developer streamer session on the
TRADING app, subscribed to ACCT_ACTIVITY, coexist with an open ThinkOrSwim
desktop session — or does one of them get dropped?

    ./scripts/run.sh schwab_stream_probe.py            # hold 120 s
    ./scripts/run.sh schwab_stream_probe.py --hold 300

What it does, in order, each step printed with a CT stamp:

1. Asks for the vault passphrase (not echoed) and opens the trading
   credential — the vault's app key and secret, and the newer of the vault's
   token and the weekly re-auth's ``trading.json``.
2. Refreshes the access token **in memory only**. Nothing is written back;
   ``execd.schwab.refresh`` preserves ``creation_timestamp``, so the seven-day
   wall does not move and the running service's own credential is untouched.
3. ``GET /trader/v1/userPreference`` for ``streamerInfo``.
4. Opens the websocket, ADMIN LOGIN, ACCT_ACTIVITY SUBS.
5. Holds for ``--hold`` seconds, printing every frame (heartbeats counted, not
   printed). Watch TOS the whole time.
6. UNSUBS, LOGOUT, close.

Every frame is also written, scrubbed, to ``data/probes/`` as JSONL — the
fixture the bead asks for. Account numbers and the access token never reach
the screen or the file.

Receive-only: the only frames it sends are LOGIN, SUBS, UNSUBS and LOGOUT. It
places nothing and cannot — there is no order call anywhere in it.

Lives in ``scripts/``, not ``execd/``, on purpose: the execd wall allows the
package one transport (httpx). Whether execd itself may hold a websocket is the
design question this probe's answer feeds; the probe does not pre-empt it.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import httpx  # noqa: E402

CT = ZoneInfo("America/Chicago")
STATE_DIR = Path("/var/lib/execd")
VAULT = STATE_DIR / "vault.json"
PROBE_DIR = REPO / "data" / "probes"

#: A run of 8+ digits is an account number or a hash of one wherever it sits.
_ACCOUNT_RUN = re.compile(r"\d{8,}")


def now_ct() -> str:
    return datetime.now(timezone.utc).astimezone(CT).strftime("%H:%M:%S CT")


def scrub(obj: Any, secrets: tuple[str, ...] = ()) -> Any:
    """The frame with account numbers and any named secret replaced.

    Recursive over dicts and lists; strings are scrubbed in place so a JSON
    payload nested as a string (ACCT_ACTIVITY's MESSAGE_DATA) is covered too.
    ACCT_ACTIVITY field "1" is the account itself and goes whole."""
    if isinstance(obj, dict):
        return {k: ("<acct>" if k == "1" else scrub(v, secrets)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(v, secrets) for v in obj]
    if isinstance(obj, str):
        for s in secrets:
            if s:
                obj = obj.replace(s, "<secret>")
        return _ACCOUNT_RUN.sub("<acct>", obj)
    return obj


def request(info: dict[str, Any], rid: int, service: str, command: str,
            parameters: dict[str, Any]) -> dict[str, Any]:
    """One streamer request frame, the shape schwab-py's ``_make_request`` builds."""
    return {"requests": [{
        "service": service,
        "requestid": str(rid),
        "command": command,
        "SchwabClientCustomerId": info["schwabClientCustomerId"],
        "SchwabClientCorrelId": info["schwabClientCorrelId"],
        "parameters": parameters,
    }]}


def is_heartbeat(frame: dict[str, Any]) -> bool:
    return set(frame) == {"notify"} and all("heartbeat" in n for n in frame["notify"])


def response_code(frame: dict[str, Any], command: str) -> int | None:
    """The content code of the response to ``command`` in this frame, if any."""
    for r in frame.get("response", []):
        if r.get("command") == command:
            return int(r.get("content", {}).get("code", -1))
    return None


def open_credential() -> tuple[str, str, str]:
    """(access token, app key, secret) — refreshed in memory, never stored."""
    from execd.schwab import Credential, new_client, refresh, trading_payload
    from execd.vault import BadPassphrase, Vault

    passphrase = getpass.getpass("vault passphrase: ")
    try:
        payload = Vault(VAULT).load(passphrase)
    except BadPassphrase:
        sys.exit("the vault did not open with that passphrase — nothing was sent")
    finally:
        del passphrase
    cred = Credential.from_payload(trading_payload(payload, STATE_DIR))
    with new_client() as client:
        wrapped = refresh(client, cred)
    return str(wrapped["token"]["access_token"]), cred.app_key, cred.secret


async def probe(hold_s: float, out: Path) -> int:
    from execd.schwab import API
    import websockets

    print(f"{now_ct()}  opening the trading credential (in memory only)")
    access, app_key, secret = open_credential()
    secrets = (access, app_key, secret)

    with httpx.Client(base_url=API, timeout=15.0) as client:
        r = client.get("/trader/v1/userPreference",
                       headers={"Authorization": f"Bearer {access}"})
    print(f"{now_ct()}  userPreference -> HTTP {r.status_code}")
    if r.status_code != 200:
        print(scrub(r.text[:400], secrets))
        return 1
    info = r.json()["streamerInfo"][0]
    print(f"{now_ct()}  streamer {info['streamerSocketUrl']}  "
          f"channel {info['schwabClientChannel']}  function {info['schwabClientFunctionId']}")

    out.parent.mkdir(parents=True, exist_ok=True)
    beats = frames = 0
    with out.open("a", encoding="utf-8") as log:
        def record(direction: str, frame: Any) -> None:
            log.write(json.dumps({"ts_ct": datetime.now(timezone.utc).astimezone(CT).isoformat(),
                                  "dir": direction, "frame": scrub(frame, secrets)}) + "\n")
            log.flush()

        async with websockets.connect(info["streamerSocketUrl"]) as ws:
            async def send(frame: dict[str, Any]) -> None:
                record("out", frame)
                await ws.send(json.dumps(frame))

            async def await_code(command: str, timeout: float = 15.0) -> int:
                deadline = time.monotonic() + timeout
                while (left := deadline - time.monotonic()) > 0:
                    frame = json.loads(await asyncio.wait_for(ws.recv(), left))
                    record("in", frame)
                    code = response_code(frame, command)
                    if code is not None:
                        return code
                raise TimeoutError(f"no {command} response in {timeout:.0f}s")

            await send(request(info, 0, "ADMIN", "LOGIN", {
                "Authorization": access,
                "SchwabClientChannel": info["schwabClientChannel"],
                "SchwabClientFunctionId": info["schwabClientFunctionId"],
            }))
            code = await await_code("LOGIN")
            print(f"{now_ct()}  LOGIN -> code {code}")
            if code != 0:
                return 1

            await send(request(info, 1, "ACCT_ACTIVITY", "SUBS", {
                "keys": info["schwabClientCorrelId"], "fields": "0,1,2,3"}))
            code = await await_code("SUBS")
            print(f"{now_ct()}  ACCT_ACTIVITY SUBS -> code {code}")
            print(f"{now_ct()}  holding {hold_s:.0f}s — WATCH TOS NOW (Ctrl-C ends early, cleanly)")

            end = time.monotonic() + hold_s
            try:
                while (left := end - time.monotonic()) > 0:
                    try:
                        frame = json.loads(await asyncio.wait_for(ws.recv(), left))
                    except asyncio.TimeoutError:
                        break
                    record("in", frame)
                    if is_heartbeat(frame):
                        beats += 1
                        continue
                    frames += 1
                    print(f"{now_ct()}  {json.dumps(scrub(frame, secrets))[:300]}")
            except websockets.ConnectionClosed as exc:
                print(f"{now_ct()}  THE STREAMER CLOSED THE SOCKET: {exc}")
                return 2
            except (KeyboardInterrupt, asyncio.CancelledError):
                print(f"{now_ct()}  ended early")

            print(f"{now_ct()}  held; {beats} heartbeats, {frames} other frames — closing")
            await send(request(info, 2, "ACCT_ACTIVITY", "UNSUBS",
                               {"keys": info["schwabClientCorrelId"]}))
            await send(request(info, 3, "ADMIN", "LOGOUT", {}))
            try:
                await await_code("LOGOUT", 5.0)
            except (TimeoutError, websockets.ConnectionClosed):
                pass
    print(f"{now_ct()}  closed. Frames: {out}")
    print("Now say what TOS did: stayed up / dropped / asked to log in again.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hold", type=float, default=120.0, help="seconds to hold the stream open")
    args = ap.parse_args(argv)
    stamp = datetime.now(timezone.utc).astimezone(CT).strftime("%Y%m%d-%H%M%S")
    out = PROBE_DIR / f"schwab_stream_{stamp}.jsonl"
    try:
        return asyncio.run(probe(args.hold, out))
    except KeyboardInterrupt:
        print(f"{now_ct()}  interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
