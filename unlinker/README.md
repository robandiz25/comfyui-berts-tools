# Unlinker

A pass-through node with a **Link / Unlink** button, so a prompt box (or any input)
can be fed by another node *or* typed in by hand without rewiring.

**Category:** `utils`

## Use

1. Wire: `source output → Unlinker → target input` (e.g. a QwenVL caption into the
   `text` box of CLIP Text Encode).
2. Click **✂️ Unlink**: the wire(s) from Unlinker to the target are removed and the
   box becomes editable again, showing whatever you last typed in it.
3. Click **🔗 Link**: the same wire(s) are put back and the source drives the box again.

- The link state and remembered targets are saved with the workflow.
- While unlinked, Unlinker and anything feeding only it (e.g. QwenVL) don't run,
  so no time or VRAM is spent on them.
- Works with any type and with more than one wire leaving the output.
- If you wire the output by hand while unlinked, the node resets to linked.
