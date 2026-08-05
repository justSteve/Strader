"""Operator alerts — code to Steve's phone, with no Claude session in the path.

[st-mk56 · Fools Remote Arm]

WHY THIS EXISTS. The Claude-native push (a session calling PushNotification)
needs three things true at once: a live session, Remote Control connected, and
the harness believing Steve is away. Measured 2026-08-05, two of the three
failed in normal use — a push was suppressed as "terminal active" seconds after
he typed, and a second was dropped with "Remote Control inactive" because the
session predated his all-sessions toggle. For a meltdown alert those are
unacceptable: a suppressed alert is indistinguishable from no alert.

So the guaranteed leg is this module. A daemon calls ``send()``; the message
reaches the phone through the vendor's push service. Nothing about Claude,
Remote Control, tmux, or a terminal is involved.

THE IOS CONSTRAINT, so nobody re-litigates it: a locked iPhone cannot be
reached directly — not over Tailscale, not over the LAN — because iOS suspends
apps. Every path goes through Apple's push service, so *some* receiver is
required. SMS is the one exception (no app at all).

BACKENDS
  pushover — recommended. $5 one-time. Holds Apple's Critical Alerts
             entitlement, so priority=2 (emergency) can break through the mute
             switch and Focus modes and repeats until acknowledged. Enable
             Critical Alerts in the Pushover app's settings; it is off by
             default and split between high and emergency priority.
  twilio   — SMS. No app on the phone at all, which makes it the best
             worst-case leg. To break through Focus: save the Twilio number as
             a contact and turn on Emergency Bypass for it — an iOS feature
             needing no app entitlement.

Configure whichever you use in .env (project root):

    ALERT_BACKEND=pushover
    PUSHOVER_TOKEN=...          # the application token
    PUSHOVER_USER=...           # your user key
    # or
    ALERT_BACKEND=twilio
    TWILIO_SID=... TWILIO_AUTH=... TWILIO_FROM=+1... TWILIO_TO=+1...

EVERY ATTEMPT IS JOURNALED to data/exec/alert-journal-<day>.jsonl — sent or
failed, with the vendor's response. An alert path nobody has verified is
exactly the artifact class the 2026-08-04 audit warned about, so verification
is built in rather than assumed: ``python -m strader.alerts --test`` sends a
real alert and prints the journal line it wrote.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from strader.config import DEFAULT_ENV_PATH, Field, load, non_empty, no_comment_residue

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
JOURNAL_DIR = PROJECT_ROOT / "data" / "exec"

PUSHOVER_URL = "https://api.pushover.net/1/messages.json"
TWILIO_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

TIMEOUT_S = 10
RETRIES = 3           # a meltdown alert is worth three tries; the loop is <1s


def _pushover_key(value: str) -> str | None:
    """Pushover keys are 30 alphanumeric chars — never an email address.

    Pushover hands a user three different identifiers and the dashboard shows
    the email gateway address prominently, so pasting the email into
    PUSHOVER_USER is the easy mistake (Steve hit exactly this 2026-08-05). It
    would fail at the API with an opaque error; catch it here with the fix.
    """
    v = value.strip()
    if "@" in v:
        return ("looks like an email address — that is Pushover's email "
                "gateway, not an API credential. PUSHOVER_USER is the 30-char "
                "user key on your dashboard; PUSHOVER_TOKEN comes from "
                "registering an app at pushover.net/apps/build")
    if not (v.isalnum() and len(v) == 30):
        return (f"should be 30 alphanumeric characters, got {len(v)} "
                f"({'non-alphanumeric' if not v.isalnum() else 'wrong length'})")
    return None


@dataclass
class AlertResult:
    ok: bool
    backend: str
    detail: str
    attempts: int

    def __bool__(self) -> bool:      # `if send(...):` reads naturally
        return self.ok


def _journal(event: dict) -> None:
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    path = JOURNAL_DIR / f"alert-journal-{day}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                             **event}) + "\n")


def _post(url: str, data: dict, auth: tuple[str, str] | None = None) -> str:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    if auth:
        import base64
        tok = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        req.add_header("Authorization", f"Basic {tok}")
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return r.read().decode()[:400]


def _pushover(cfg: dict, title: str, message: str, *, urgent: bool) -> str:
    data = {
        "token": cfg["PUSHOVER_TOKEN"], "user": cfg["PUSHOVER_USER"],
        "title": title, "message": message,
        # 2 = emergency: repeats until acknowledged, and is the priority the
        # app's Critical Alerts setting can attach to. 1 = high (bypasses the
        # quiet hours schedule but not the mute switch).
        "priority": 2 if urgent else 1,
    }
    if urgent:
        data.update({"retry": 60, "expire": 1800})   # re-alert 1/min for 30 min
    return _post(PUSHOVER_URL, data)


def _twilio(cfg: dict, title: str, message: str, *, urgent: bool) -> str:
    return _post(
        TWILIO_URL.format(sid=cfg["TWILIO_SID"]),
        {"From": cfg["TWILIO_FROM"], "To": cfg["TWILIO_TO"],
         "Body": f"{title}: {message}"[:1500]},
        auth=(cfg["TWILIO_SID"], cfg["TWILIO_AUTH"]))


_BACKENDS = {
    "pushover": (_pushover, ("PUSHOVER_TOKEN", "PUSHOVER_USER")),
    "twilio": (_twilio, ("TWILIO_SID", "TWILIO_AUTH", "TWILIO_FROM", "TWILIO_TO")),
}


def _config(env_path=DEFAULT_ENV_PATH) -> tuple[str, dict]:
    backend = load((Field("ALERT_BACKEND", validators=(non_empty, no_comment_residue)),),
                   env_path=env_path)["ALERT_BACKEND"].strip().lower()
    if backend not in _BACKENDS:
        raise RuntimeError(
            f"ALERT_BACKEND={backend!r} is not one of {sorted(_BACKENDS)}")
    _, keys = _BACKENDS[backend]
    fields = tuple(
        Field(k, secret=True,
              validators=(non_empty, no_comment_residue)
                         + ((_pushover_key,) if k.startswith("PUSHOVER_") else ()))
        for k in keys)
    return backend, load(fields, env_path=env_path)


def send(title: str, message: str, *, urgent: bool = True,
         env_path=DEFAULT_ENV_PATH) -> AlertResult:
    """Send an alert to Steve's phone. Never raises — always journals.

    ``urgent=True`` asks the backend for its break-through-anything treatment
    (Pushover emergency priority, repeating until acknowledged). Use it for the
    events Steve would want to be woken for and nothing else: an alert that
    cries wolf gets its notifications turned off, which is the real failure.
    """
    try:
        backend, cfg = _config(env_path)
    except Exception as e:                      # missing/invalid config
        detail = f"config error: {type(e).__name__}: {e}"
        logger.error("alert NOT sent — %s", detail)
        _journal({"event": "alert_failed", "backend": None, "title": title,
                  "urgent": urgent, "detail": detail, "attempts": 0})
        return AlertResult(False, "none", detail, 0)

    fn, _ = _BACKENDS[backend]
    last = ""
    for attempt in range(1, RETRIES + 1):
        try:
            resp = fn(cfg, title, message, urgent=urgent)
            logger.info("alert sent via %s (attempt %d)", backend, attempt)
            _journal({"event": "alert_sent", "backend": backend, "title": title,
                      "message": message, "urgent": urgent,
                      "response": resp, "attempts": attempt})
            return AlertResult(True, backend, resp, attempt)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            last = f"{type(e).__name__}: {e}"
            logger.warning("alert attempt %d/%d failed via %s — %s",
                           attempt, RETRIES, backend, last)
    _journal({"event": "alert_failed", "backend": backend, "title": title,
              "message": message, "urgent": urgent, "detail": last,
              "attempts": RETRIES})
    return AlertResult(False, backend, last, RETRIES)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Operator alert — code to phone")
    ap.add_argument("--test", action="store_true",
                    help="send a real test alert and show the journal line")
    ap.add_argument("--title", default="Strader test")
    ap.add_argument("--message", default="Alert path verification — no action needed.")
    ap.add_argument("--calm", action="store_true",
                    help="normal priority instead of break-through urgent")
    args = ap.parse_args()
    if not args.test:
        ap.print_help()
        return 2
    r = send(args.title, args.message, urgent=not args.calm)
    print(f"{'SENT' if r.ok else 'FAILED'} via {r.backend} "
          f"after {r.attempts} attempt(s)\n  {r.detail}")
    if not r.ok and r.backend == "none":
        print("\nConfigure .env first — see this module's docstring:\n"
              "  ALERT_BACKEND=pushover / PUSHOVER_TOKEN / PUSHOVER_USER")
    return 0 if r.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
