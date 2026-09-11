"""The trade blotter — registered rules scored as trades. [st-djb9, st-uc23]

Stage 3 of the refactor-and-blotter plan (``docs/a2a/2026-08-29-coo-to-strader-
refactor-and-blotter-plan.md`` §5, amended by Strader's 2026-08-30 counter §5).

:mod:`strader.blotter.rules`   the registry — a predictive entity's ``rule:`` block
                               joined to ``scripts/measurement/rules/<id>.py``
:mod:`strader.blotter.state`   the state a rule reads at its fire minute (the
                               final-hour lenses, data before T only)
:mod:`strader.blotter.legs`    the instrument and its marks: the ~10-ITM 0DTE
                               single priced from its own prints, or from the
                               estimated mark path where no prints exist
:mod:`strader.blotter.rows`    the row schema, its id, and the exit resolution
"""
