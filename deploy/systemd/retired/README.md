# Retired units

Unit files kept for the record and for a re-subscription; `deploy/install.sh`
installs only `deploy/systemd/*.service|*.timer`, so nothing here is copied,
enabled or started. To bring one back: `git mv` it up one level, run
`bash deploy/install.sh`, and re-add the sentinel to install.sh's start list.

| unit | retired | why |
|------|---------|-----|
| `strader-gexbot-orderflow-1s.{service,timer}` | 2026-09-08 | `/SPX/orderflow/orderflow` is Quant-only; on State it answers HTTP 403 `User is not subscribed to Orderflow package` (measured 08:30:02 CT, st-x3tx). A daily unit whose only outcome is a denial. |
| `strader-orderflow-sentinel.service` | 2026-09-08 | Its only input is `gexbot_orderflow_1s.jsonl`, written by the unit above; with that denied it heartbeats `rows=0` forever (st-x3tx). |

The installed copies under `/etc/systemd/system/` are disabled by Steve
(`systemctl disable --now …`, ask on the bridge 2026-09-08) — the agent may not
stop a live unit.
