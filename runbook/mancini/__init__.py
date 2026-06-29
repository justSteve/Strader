"""Mancini Runbook pilot: newsletter -> validated levels + commentary store.

Pipeline (see run.py):
    raw newsletter text
      -> llm.extract()      bounded Claude call, forced tool_use -> structured JSON
      -> validate.check()   anti-hallucination: every price must appear in source
      -> store.append()     append-only JSONL commentary store
      -> (chart prompt + morning brief, future steps)

The LLM is a pure function (text in -> validated JSON out): no tools, no agent,
no session. Bead co-7lyf.
"""
