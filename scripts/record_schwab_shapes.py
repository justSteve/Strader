#!/usr/bin/env python3
"""Record Schwab Trader API response SHAPES for the execution service. [st-w2nw]

One-off, read-only, plain HTTPS. This script imports neither ``schwab`` (the
hobbled fork) nor ``broker_schwab`` (the gated factory); it speaks to the
Trader API the way ``execd/schwab.py`` will — an access token in a header —
because the point is to record what that transport will actually see.

WHY IT EXISTS. Stage 2 of the live execution service (epic st-5qjq) is a
client for endpoints this repo had never called: account numbers, positions,
order history, a single order. Writing that client from memory of the spec
would look finished and would not be — a wrong field name there becomes a
rejected order with Steve at the button in stage 4. So the shapes are recorded
first and the client is written against them.

WHAT IT MAY CALL. Steve's ruling of 2026-08-30 ("agreed per terms listed"):
read-only calls with the current token — account numbers, prices, chains,
positions — never an order call of any kind. Desk's rider of the same day adds
the order-history GET, same terms. Every request here is a GET. There is no
code path in this file that can POST, PUT or DELETE against ``/trader``.

WHAT IT WRITES. ``tests/fixtures/schwab/<name>.json`` — the response body with
every account identifier replaced at capture time (Desk's other rider: scrub
before anything lands in a repo every agent reads). Account numbers and hashes
are learned from the accountNumbers response and replaced everywhere they
occur in every capture, as strings and as bare integers. A sidecar
``_capture.json`` records when each capture was taken, the market state label
given on the command line, the request (with the hash already scrubbed), the
status and the size. Token values are never written, printed or logged.

THE TOKEN. Read from ``SCHWAB_TOKEN_PATH`` in the schwab-py wrapped shape
(``{"creation_timestamp", "token": {...}}``). If the access token is within
two minutes of expiry it is refreshed against Schwab's token endpoint with the
refresh token, exactly as the library does, and the file is rewritten in the
same shape with ``creation_timestamp`` preserved — so the 7-day wall assessed
by ``strader.schwab_token`` is unchanged and the pre-approved readers keep
working. Refreshing the access token does not extend the refresh token.

    .venv/bin/python scripts/record_schwab_shapes.py --label "RTH, 2026-09-04 09:10 CT"
    .venv/bin/python scripts/record_schwab_shapes.py --label pre-open --out /tmp/x --strikes 60

Exit 0 when every capture succeeded, 1 otherwise; the summary names the ones
that did not.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from strader.settings import load_schwab  # noqa: E402  (reads .env; imports no broker code)

API = "https://api.schwabapi.com"
TOKEN_ENDPOINT = f"{API}/v1/oauth/token"
DEFAULT_OUT = REPO / "tests" / "fixtures" / "schwab"
REFRESH_LEEWAY_S = 120
TIMEOUT_S = 20.0


# ── token ────────────────────────────────────────────────────────────────


def _token_path(cfg: dict[str, str]) -> Path:
    raw = cfg.get("SCHWAB_TOKEN_PATH") or "./tokens/schwab_token.json"
    p = Path(raw)
    return p if p.is_absolute() else (REPO / raw).resolve()


def load_token(path: Path) -> dict[str, Any]:
    wrapped = json.loads(path.read_text(encoding="utf-8"))
    if "token" not in wrapped or "creation_timestamp" not in wrapped:
        raise SystemExit(f"token file at {path} is not in schwab-py's wrapped shape")
    return wrapped


def write_token(path: Path, wrapped: dict[str, Any]) -> None:
    """Atomic, 0600, same shape the library writes."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".schwab_token.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(wrapped, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def refresh_access_token(client: httpx.Client, wrapped: dict[str, Any],
                         api_key: str, app_secret: str) -> dict[str, Any]:
    """POST grant_type=refresh_token. Returns the new wrapped token; never logs it."""
    old = wrapped["token"]
    basic = base64.b64encode(f"{api_key}:{app_secret}".encode()).decode()
    r = client.post(
        TOKEN_ENDPOINT,
        headers={"Authorization": f"Basic {basic}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "refresh_token", "refresh_token": old["refresh_token"]},
    )
    if r.status_code != 200:
        raise SystemExit(f"token refresh failed: HTTP {r.status_code} "
                         f"(body {len(r.content)} bytes, not shown)")
    new = r.json()
    if "access_token" not in new:
        raise SystemExit("token refresh answered 200 without an access_token")
    new.setdefault("refresh_token", old["refresh_token"])
    new["expires_at"] = int(time.time()) + int(new.get("expires_in", 1800))
    rotated = new["refresh_token"] != old["refresh_token"]
    print(f"[token] access token refreshed; refresh token "
          f"{'ROTATED' if rotated else 'unchanged'}; expires_in={new.get('expires_in')}")
    return {"creation_timestamp": wrapped["creation_timestamp"], "token": new}


# ── scrubbing ────────────────────────────────────────────────────────────


class Scrubber:
    """Learns account identifiers once, replaces them everywhere.

    Replacement happens on the serialized text, so an identifier that appears
    as a bare integer (``"accountNumber": 12345678`` in an order) is caught as
    well as the string form. Placeholders keep the field's type: a number
    becomes a different number, a string a different string."""

    def __init__(self) -> None:
        self.numbers: dict[str, str] = {}   # real account number -> "ACCT-n"
        self.hashes: dict[str, str] = {}    # real hash -> "HASH-n"

    def learn(self, account_numbers: list[dict[str, Any]]) -> None:
        for i, entry in enumerate(account_numbers, start=1):
            num = str(entry.get("accountNumber", "")).strip()
            hsh = str(entry.get("hashValue", "")).strip()
            if num:
                self.numbers[num] = f"ACCT-{i}"
            if hsh:
                self.hashes[hsh] = f"HASH-{i}"

    def placeholder_number(self, real: str) -> int:
        """A bare-integer stand-in that keeps the JSON type: 9000000n."""
        idx = list(self.numbers).index(real) + 1
        return 90000000 + idx

    def scrub_text(self, text: str) -> str:
        for real, ph in sorted(self.hashes.items(), key=lambda kv: -len(kv[0])):
            text = text.replace(real, ph)
        for real, ph in sorted(self.numbers.items(), key=lambda kv: -len(kv[0])):
            # quoted string form
            text = text.replace(f'"{real}"', f'"{ph}"')
            # bare integer form, only as a whole JSON number token
            text = re.sub(rf'(?<![\d"])({re.escape(real)})(?![\d"])',
                          str(self.placeholder_number(real)), text)
        return text

    def scrub(self, obj: Any) -> Any:
        return json.loads(self.scrub_text(json.dumps(obj)))

    def scrub_path(self, path: str) -> str:
        for real, ph in self.hashes.items():
            path = path.replace(real, ph)
        return path


# ── capture ──────────────────────────────────────────────────────────────


class Recorder:
    def __init__(self, client: httpx.Client, token: str, out: Path, label: str,
                 scrubber: Scrubber) -> None:
        self.client = client
        self.token = token
        self.out = out
        self.label = label
        self.scrubber = scrubber
        self.meta: dict[str, Any] = {}
        self.failures: list[str] = []

    def get(self, name: str, path: str, params: dict[str, Any] | None = None,
            *, write: bool = True) -> Any:
        url = f"{API}{path}"
        started = time.monotonic()
        try:
            r = self.client.get(url, params=params,
                                headers={"Authorization": f"Bearer {self.token}",
                                         "Accept": "application/json"})
        except httpx.HTTPError as exc:
            self.failures.append(f"{name}: transport error {type(exc).__name__}")
            self.meta[name] = {"path": self.scrubber.scrub_path(path), "params": params,
                               "error": type(exc).__name__}
            print(f"  {name:<22} transport error: {type(exc).__name__}")
            return None
        elapsed_ms = int((time.monotonic() - started) * 1000)

        body: Any
        try:
            body = r.json()
        except ValueError:
            body = {"_non_json_body_bytes": len(r.content)}

        entry = {
            "captured_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "market_state": self.label,
            "method": "GET",
            "path": self.scrubber.scrub_path(path),
            "params": params or {},
            "status": r.status_code,
            "elapsed_ms": elapsed_ms,
            "bytes": len(r.content),
        }
        self.meta[name] = entry

        top = sorted(body) if isinstance(body, dict) else f"list[{len(body)}]" if isinstance(body, list) else type(body).__name__
        print(f"  {name:<22} HTTP {r.status_code}  {len(r.content):>7} B  {elapsed_ms:>5} ms  {top}")

        if r.status_code != 200:
            self.failures.append(f"{name}: HTTP {r.status_code}")
            if write:
                self._write(f"{name}.error", self.scrubber.scrub(body))
            return None
        if write:
            self._write(name, self.scrubber.scrub(body))
        return body

    def _write(self, name: str, body: Any) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / f"{name}.json").write_text(json.dumps(body, indent=2, sort_keys=True) + "\n",
                                               encoding="utf-8")

    def finish(self) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "_capture.json").write_text(
            json.dumps({"recorded_by": "scripts/record_schwab_shapes.py",
                        "label": self.label,
                        "identifiers_scrubbed": {"account_numbers": len(self.scrubber.numbers),
                                                 "account_hashes": len(self.scrubber.hashes)},
                        "captures": self.meta}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def first_option_symbol(chain: dict[str, Any]) -> str | None:
    for key in ("callExpDateMap", "putExpDateMap"):
        for _exp, strikes in (chain.get(key) or {}).items():
            for _strike, contracts in strikes.items():
                for c in contracts:
                    if c.get("symbol"):
                        return str(c["symbol"])
    return None


def pick_order_id(orders: list[dict[str, Any]]) -> str | None:
    """Prefer a FILLED option order — the exact shape place() then get_order() will meet."""
    best: tuple[int, str] | None = None
    for o in orders:
        oid = o.get("orderId")
        if oid is None:
            continue
        score = 0
        if o.get("status") == "FILLED":
            score += 2
        legs = o.get("orderLegCollection") or []
        if any((leg.get("instrument") or {}).get("assetType") == "OPTION" for leg in legs):
            score += 1
        if best is None or score > best[0]:
            best = (score, str(oid))
    return best[1] if best else None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--label", required=True,
                   help="market state at capture, e.g. 'pre-open 2026-09-04 08:05 CT' — "
                        "stored beside every capture so a stale quote is never mistaken for a live one")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"fixture directory (default {DEFAULT_OUT})")
    p.add_argument("--strikes", type=int, default=24, help="strikeCount for the chain capture")
    p.add_argument("--days", type=int, default=60, help="order-history window, days back (Schwab max 60 per call)")
    p.add_argument("--underlying", default="$SPX")
    p.add_argument("--market-only", action="store_true",
                   help="record the market-data endpoints only (quotes, chain). Measured "
                        "2026-09-04: the app answered 401 'no apiproduct match found' on every "
                        "/trader path — the Accounts and Trading product was not on the app.")
    args = p.parse_args(argv)

    cfg = load_schwab()
    api_key, app_secret = cfg["SCHWAB_API_KEY"], cfg["SCHWAB_APP_SECRET"]
    tpath = _token_path(cfg)
    if not tpath.exists():
        print(f"no token at {tpath}; run scripts/refresh_schwab_token.py first", file=sys.stderr)
        return 1
    wrapped = load_token(tpath)

    with httpx.Client(timeout=TIMEOUT_S) as client:
        tok = wrapped["token"]
        if int(tok.get("expires_at", 0)) - int(time.time()) < REFRESH_LEEWAY_S:
            wrapped = refresh_access_token(client, wrapped, api_key, app_secret)
            write_token(tpath, wrapped)
            print(f"[token] file rewritten in place ({tpath.name}); creation_timestamp preserved")
        else:
            left = int(tok["expires_at"]) - int(time.time())
            print(f"[token] access token valid for {left}s; no refresh needed")
        access = wrapped["token"]["access_token"]

        scrub = Scrubber()
        rec = Recorder(client, access, args.out, args.label, scrub)
        print(f"[record] label={args.label!r} out={args.out}")

        now = datetime.now(timezone.utc)
        if not args.market_only:
            # 1. account numbers → the identifiers to scrub, and the hash for the rest
            nums = rec.get("account_numbers", "/trader/v1/accounts/accountNumbers", write=False)
            if not isinstance(nums, list) or not nums:
                print("accountNumbers did not answer with a list; no other /trader path is "
                      "safe to record. If the status was 401 'no apiproduct match found', the "
                      "app lacks the Accounts and Trading product — Steve's developer portal. "
                      "Re-run with --market-only for the market-data shapes.", file=sys.stderr)
                rec.finish()
                return 1
            scrub.learn(nums)
            rec._write("account_numbers", scrub.scrub(nums))
            acct_hash = str(nums[0]["hashValue"])
            print(f"  (learned {len(scrub.numbers)} account number(s), {len(scrub.hashes)} hash(es); scrubbing from here on)")

            # 2. positions — all linked accounts, then the one account by hash
            rec.get("accounts_positions", "/trader/v1/accounts", {"fields": "positions"})
            rec.get("account_positions", f"/trader/v1/accounts/{acct_hash}", {"fields": "positions"})

            # 3. order history (Desk's rider: GET-only) and one order by id
            orders = rec.get("orders", f"/trader/v1/accounts/{acct_hash}/orders",
                             {"fromEnteredTime": _iso_z(now - timedelta(days=args.days)),
                              "toEnteredTime": _iso_z(now), "maxResults": 200})
            if isinstance(orders, list) and orders:
                statuses: dict[str, int] = {}
                for o in orders:
                    statuses[str(o.get("status"))] = statuses.get(str(o.get("status")), 0) + 1
                print(f"  (orders in window: {len(orders)}; by status {statuses})")
                oid = pick_order_id(orders)
                if oid:
                    rec.get("order_by_id", f"/trader/v1/accounts/{acct_hash}/orders/{oid}")
            else:
                print("  (no orders in the window — order_by_id not captured)")

        # 4. prices: the index and the front future
        quotes = rec.get("quotes_index", "/marketdata/v1/quotes",
                         {"symbols": f"{args.underlying},/ES", "indicative": "false"})

        # 5. the chain, small, nearest expiries only
        today = now.astimezone(timezone.utc).date()
        chain = rec.get("chain", "/marketdata/v1/chains",
                        {"symbol": args.underlying, "contractType": "ALL",
                         "strikeCount": args.strikes, "strategy": "SINGLE",
                         "fromDate": today.isoformat(),
                         "toDate": (today + timedelta(days=3)).isoformat()})

        # 6. one option quote, by the symbol the chain itself uses
        if isinstance(chain, dict):
            sym = first_option_symbol(chain)
            if sym:
                print(f"  (option symbol form as the chain spells it: {sym!r}, {len(sym)} chars)")
                rec.get("quotes_option", "/marketdata/v1/quotes", {"symbols": sym})

        rec.finish()

    if rec.failures:
        print("\nFAILED: " + "; ".join(rec.failures), file=sys.stderr)
        return 1
    print(f"\nrecorded {len(rec.meta)} captures to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
