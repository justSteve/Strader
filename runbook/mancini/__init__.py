"""Mancini Runbook pilot: newsletter -> validated levels + commentary store.

Pipeline (see run.py):
    raw newsletter text
      -> listlevels.extract_list_levels()  regex scrape of the explicit
                                           Supports/Resistances lists — no judgment
      -> the in-session extraction          an agent reads the letter and writes
                                           the JSON; passed in via --extraction-json
      -> validate.check()   anti-hallucination: every price must appear in source
      -> store.append()     append-only JSONL commentary store
      -> chart Pine + desk plan doc + morning brief

Nothing here calls a model. The interpretive leg is a prompt parse performed by
whatever agent is holding the letter, against the contract in
extraction-contract.md; the package only validates and persists what it is
handed. Beads co-7lyf, st-26q5.
"""
