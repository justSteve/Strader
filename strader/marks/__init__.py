"""Mark paths for the blotter — what a position was worth, minute by minute. [st-9hhc]

Two kinds of mark path exist and they must never be pooled:

* **printed** — the option's own OPRA prints. The truth, where it exists,
  which is 13:00-15:00 CT and nowhere earlier on any corpus day.
* **estimated** — :mod:`strader.marks.estimated`, a per-minute ES->premium
  proxy calibrated against the printed path over the same window. It is a
  model, and every row it produces says so.

The estimated path exists so that an estimated blotter row can carry an exit
other than ``time`` — a stop or a target — *once the validation says the proxy
fires them when the prints do*. Until that measurement lands, the standing
contract holds: estimated rows resolve ``exit_reason=time`` only, and every
aggregate splits by mark path.
"""
