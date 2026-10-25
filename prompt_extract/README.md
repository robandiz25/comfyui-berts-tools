# Prompt Extract

Drop an image in and get the **positive** and **negative** prompts it was made with, as `STRING` outputs you can wire straight into text encoders.

## Nodes

**Load Image (Extract Prompts)** — works like the stock Load Image (upload / drag-and-drop), with extra outputs:

| Output | Type | Notes |
|---|---|---|
| `image`, `mask` | IMAGE, MASK | Same as Load Image |
| `positive` | STRING | Positive prompt from the file's metadata |
| `negative` | STRING | Negative prompt; empty when the workflow had none (Flux `BasicGuider`, `ConditioningZeroOut`) |
| `source_metadata` | IMAGE_META | Wire into **Save Image (Source Metadata)** if you want to keep the original workflow |
| `filename` | STRING | File name without extension |

### Link prompts toggle

The node has a **link prompts** toggle:

- **Off (unlinked)** removes the links from `positive` / `negative`, so the prompt boxes on the nodes they fed show their own typed text again. The node remembers where those links went.
- **On (linked)** reconnects them to the same inputs.

The toggle's position and the remembered links are saved with the workflow. (Bypassing the node doesn't do this: a bypassed node keeps its links, so the prompt boxes stay hidden.)

**Extract Prompts (Metadata)** — takes a `source_metadata` link (e.g. from **Read Image Metadata (Path)** fed by a batch loader) and outputs `positive` / `negative`.

## What it can read

- **ComfyUI images** — follows the saved graph from the sampler's `positive` / `negative` inputs back to the text encoder, through FluxGuidance, conditioning combine/concat, ControlNet apply, primitive / string / string-concatenate nodes, and Impact wildcard encoders. Works with `KSampler`, `KSamplerAdvanced`, `SamplerCustom(Advanced)` + `CFGGuider` / `BasicGuider`, and detailer nodes. When a workflow has several samplers, the first `KSampler` (lowest node ID) with a resolvable prompt wins.
- **LLM prompt enhancers** (TextGenerate, Ollama, LM Studio, Gemini, etc.) — ComfyUI only saves an enhancer's *inputs*, not the prompt it generated, so without special handling you'd get the instruction template back. Instead the node returns:
  1. the **expanded prompt**, if a Show Text / Preview / Display node was showing the enhancer's output (its text is saved in the workflow), otherwise
  2. **your original input** to the enhancer, with the instruction template (everything up to `User's Input:` etc.) stripped off.

  The console log says which: `comfyui (llm output)` or `comfyui (llm input)`. To make the expanded prompt recoverable, add a Show Text node off the enhancer's output.
- **A1111 / Forge / Civitai images** — splits the `parameters` text on `Negative prompt:` and drops the `Steps: …` settings line.
- PNG text chunks, JPEG/WebP EXIF UserComment, and ComfyUI WebP EXIF tags (via Source Metadata's reader).

If no prompt is found, both outputs are empty strings and the console prints `[PromptExtract] <file>: no prompt found in metadata`.
