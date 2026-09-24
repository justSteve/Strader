"""Two instances side by side, one per broker. [co-8mb1z]

Steve, 2026-09-24: "I need sep forms for Alpaca and Schwab. I'll be wanting
to create and manage positions in both throughout the day." So the Schwab
instance keeps /exec on 8778/8779 with state in /var/lib/execd, and the
Alpaca instance runs the same code at /exec-alpaca on 8780/8781 with state
in /var/lib/execd-alpaca. What is asserted here:

- every link, form action, poll URL and redirect a page emits stays inside
  its own instance's prefix — on every page, with a position live;
- each page carries its broker badge next to PAPER/LIVE, and the journal
  names the broker on every line;
- two instances cannot share a state directory;
- the two unit files separate state, config, ports and prefix, and only the
  Schwab unit can write the vault and the market grant;
- the Alpaca page never writes a Schwab grant, and the market grant the
  Schwab page writes reaches the reader in the other process without a
  restart.
"""

from __future__ import annotations

import json
import re
from configparser import ConfigParser
from pathlib import Path

import pytest

from execd.page import CredentialFile, create_page
from execd.service import ExecService, ServiceConfig
from execd.vault import Vault

from .conftest import CALL, Clock, page_send, same_origin, schwab_chain_maps
from .test_page import PASS, market_payload, vault_payload

REPO = Path(__file__).resolve().parents[2]
UNITS = REPO / "deploy" / "systemd"

URL_ATTR = re.compile(r"""(?:href|action)=['"]([^'"]*)['"]""")
#: a quoted page path inside a script or a JSON body (file paths such as the
#: STOP file's are in the status JSON too, and are not URLs)
QUOTED_PATH = re.compile(r"""["'](/exec[^"'\s<>]*)["']""")


def emitted_urls(body: str) -> list[str]:
    urls = URL_ATTR.findall(body) + QUOTED_PATH.findall(body)
    return [u for u in urls if u.startswith("/")]


def inside(prefix: str, urls: list[str]) -> list[str]:
    """The URLs that escaped ``prefix``."""
    return [u for u in urls if not (u == prefix or u.startswith(prefix + "/")
                                    or u.startswith(prefix + "?"))]


@pytest.fixture
def two_pages(broker, clock: Clock, tmp_path, bounds):
    """A Schwab-shaped instance at /exec and an Alpaca-shaped one at
    /exec-alpaca, each over its own mock and its own state directory,
    sharing one vault and one market file the way the units do."""
    broker.set_chain("SPXW", schwab_chain_maps())
    vault = Vault(tmp_path / "shared" / "vault.json")
    env = vault_payload()
    env["alpaca"] = {"paper": {"key_id": "PK", "secret_key": "S"}}
    vault.store(env, PASS)
    mfile = tmp_path / "shared" / "market.json"
    mfile.write_text(json.dumps(market_payload()))
    pages = {}
    for name, prefix, grants in (("schwab", "/exec", True), ("alpaca", "/exec-alpaca", False)):
        svc = ExecService(broker, ServiceConfig(state_dir=tmp_path / name, bounds=bounds,
                                                sha="t", mode="paper", broker=name),
                          clock=clock)
        svc.unlock({"token": "mock"})
        market = CredentialFile(mfile)
        market.load()
        app = create_page(svc, vault=vault, market=market, clock=clock, prefix=prefix,
                          grants=grants)
        app.config["TESTING"] = True
        pages[name] = (svc, same_origin(app.test_client()), market)
    return pages


class TestPrefix:
    @pytest.mark.parametrize("name,prefix", [("schwab", "/exec"), ("alpaca", "/exec-alpaca")])
    def test_every_url_on_every_page_stays_inside_its_prefix(self, two_pages, name, prefix):
        svc, page, _ = two_pages[name]
        sel = {"side": "call", "strike": "6400"}
        r = page_send(page, sel, prefix)
        assert r.status_code == 303 and r.headers["Location"].startswith(prefix + "/")
        assert svc.status()["positions"], "a live position, so the bracket editor renders"
        seen: list[str] = []
        bodies = [
            page.get(prefix + "/").get_data(as_text=True),
            page.get(prefix + "/order?side=call&strike=6400").get_data(as_text=True),
            page.get(prefix + "/account").get_data(as_text=True),
            json.dumps(page.get(f"{prefix}/order/state?side=call&strike=6400").json),
            json.dumps(page.get(f"{prefix}/order/price?side=call&strike=6400").json),
            page.post(prefix + "/flatten", data={}).get_data(as_text=True),
            page.post(prefix + "/lock", data={}).get_data(as_text=True),
        ]
        for body in bodies:
            seen += emitted_urls(body)
        assert len(seen) > 20, seen
        assert inside(prefix, seen) == []
        # redirects too
        for path in ("/stop", "/stand-down"):
            loc = page.post(prefix + path, data={}).headers.get("Location", "")
            assert loc.startswith(prefix + "/"), (path, loc)

    def test_the_other_instances_prefix_is_not_served(self, two_pages):
        _, alpaca, _ = two_pages["alpaca"]
        _, schwab, _ = two_pages["schwab"]
        assert alpaca.get("/exec/account").status_code == 404
        assert schwab.get("/exec-alpaca/account").status_code == 404

    def test_a_prefix_that_is_not_one_segment_is_refused(self, tmp_path):
        from execd.__main__ import main
        for bad in ("exec", "/exec/alpaca", "/Exec", "/"):
            assert main(["--mock", "--page-prefix", bad, "--state-dir", str(tmp_path)]) == 2


class TestBadges:
    @pytest.mark.parametrize("name,word", [("schwab", "SCHWAB"), ("alpaca", "ALPACA")])
    def test_the_broker_badge_sits_beside_paper_on_both_pages(self, two_pages, name, word):
        svc, page, _ = two_pages[name]
        prefix = "/exec" if name == "schwab" else "/exec-alpaca"
        for path in ("/", "/account"):
            body = page.get(prefix + path).get_data(as_text=True)
            badge = f"<span class='badge broker {name}'>{word}</span>"
            assert badge + "<span class='badge paper'>PAPER</span>" in body, path
            other = "ALPACA" if word == "SCHWAB" else "SCHWAB"
            assert f">{other}</span>" not in body

    def test_the_journal_names_the_broker_on_every_line(self, two_pages):
        for name in ("schwab", "alpaca"):
            svc = two_pages[name][0]
            lines = [json.loads(x) for x in svc.journal.path_for().read_text().splitlines()]
            assert lines and {e["broker"] for e in lines} == {name}

    def test_status_says_which_broker(self, two_pages):
        assert two_pages["alpaca"][0].status()["broker"] == "alpaca"


class TestStateDirs:
    def test_two_instances_cannot_share_one(self, tmp_path):
        import os
        from execd.__main__ import StateDirTaken, claim_state_dir
        fd = claim_state_dir(tmp_path / "execd")
        try:
            with pytest.raises(StateDirTaken):
                claim_state_dir(tmp_path / "execd")
            other = claim_state_dir(tmp_path / "execd-alpaca")
            os.close(other)
        finally:
            os.close(fd)
        os.close(claim_state_dir(tmp_path / "execd"))   # released with its holder

    def test_the_instances_journal_and_stop_apart(self, two_pages):
        schwab, alpaca = two_pages["schwab"][0], two_pages["alpaca"][0]
        assert schwab.journal.dir != alpaca.journal.dir
        schwab.stop()
        assert schwab.arming.killed and not alpaca.arming.killed


def unit(name: str) -> dict[str, str]:
    cp = ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read(UNITS / name)
    svc = dict(cp["Service"])
    svc["ExecStart"] = " ".join(svc["ExecStart"].replace("\\\n", " ").split())
    return svc


def flag(execstart: str, name: str, default: str) -> str:
    parts = execstart.split()
    return parts[parts.index(name) + 1] if name in parts else default


class TestUnits:
    def test_the_units_separate_state_config_ports_and_prefix(self):
        s, a = unit("strader-execd.service"), unit("strader-execd-alpaca.service")
        assert "--schwab" in s["ExecStart"] and "--alpaca" in a["ExecStart"]
        pairs = {
            "--state-dir": ("/var/lib/execd", "/var/lib/execd-alpaca"),
            "--bounds": ("/etc/execd/bounds.yaml", "/etc/execd-alpaca/bounds.yaml"),
            "--mode-file": ("/etc/execd/mode", "/etc/execd-alpaca/mode"),
            "--port": ("8778", "8780"),
            "--page-port": ("8779", "8781"),
            "--page-prefix": ("/exec", "/exec-alpaca"),
        }
        defaults = {"--mode-file": "/etc/execd/mode", "--port": "8778",
                    "--page-port": "8779", "--page-prefix": "/exec"}
        for f, (want_s, want_a) in pairs.items():
            assert flag(s["ExecStart"], f, defaults.get(f, "")) == want_s, f
            assert flag(a["ExecStart"], f, defaults.get(f, "")) == want_a, f

    def test_only_the_schwab_unit_can_write_the_grants(self):
        s, a = unit("strader-execd.service"), unit("strader-execd-alpaca.service")
        assert s["ProtectSystem"] == a["ProtectSystem"] == "strict"
        assert s["ReadWritePaths"].split() == ["/var/lib/execd"]
        assert a["ReadWritePaths"].split() == ["/var/lib/execd-alpaca"]
        # the Alpaca unit reads both from the Schwab state dir, read-only
        assert flag(a["ExecStart"], "--vault", "") == "/var/lib/execd/vault.json"
        assert flag(a["ExecStart"], "--market-credential", "") == "/var/lib/execd/market.json"

    def test_install_starts_both(self):
        text = (REPO / "deploy" / "install.sh").read_text()
        assert 'systemctl restart "$EXECD_UNIT"' in text
        assert 'systemctl restart "$ALPACA_UNIT"' in text
        assert "strader-execd-alpaca.service" in text


class TestOneGrantWriter:
    def test_the_alpaca_page_refuses_reauthorisation_and_does_not_offer_it(self, two_pages):
        _, page, market = two_pages["alpaca"]
        before = market.path.read_bytes()
        body = page.get("/exec-alpaca/account").get_data(as_text=True)
        assert "re-authorise" not in body
        for path in ("/reauth/link", "/reauth/store"):
            r = page.post("/exec-alpaca" + path, data={"app": "market", "passphrase": PASS,
                                                       "state": "x", "received_url": "x"})
            assert r.status_code == 303 and "Schwab+page" in r.headers["Location"]
        assert market.path.read_bytes() == before

    def test_the_schwab_page_still_offers_it(self, two_pages):
        body = two_pages["schwab"][1].get("/exec/account").get_data(as_text=True)
        assert "re-authorise" in body

    def test_a_grant_the_writer_saves_reaches_the_reader_without_a_restart(self, two_pages):
        _, _, writer = two_pages["schwab"]
        _, _, reader = two_pages["alpaca"]
        fresh = market_payload("market-refresh-new")
        writer.save(fresh)
        assert reader.current()["token"]["token"]["refresh_token"] == "market-refresh-new"
