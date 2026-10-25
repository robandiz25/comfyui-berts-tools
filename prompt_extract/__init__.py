"""
Prompt Extract
--------------
Drop an image in, get its positive and negative prompts out as STRINGs.

Nodes:
  * Load Image (Extract Prompts)   - Load Image + positive/negative prompt outputs
  * Extract Prompts (Metadata)     - same parsing, from a source_metadata link
                                     (pair with Read Image Metadata (Path) for batch loaders)

Understands:
  * ComfyUI images  - walks the saved API graph ("prompt" chunk) from the sampler's
                      positive/negative inputs back to the text encoders, following
                      links through string/primitive/concat nodes.
  * A1111 / Forge / Civitai images - splits the "parameters" text on "Negative prompt:".

Reuses the metadata reader from Source Metadata, so PNG text chunks, JPEG/WebP EXIF
UserComment and ComfyUI WebP EXIF tags all work. No extra pip installs.
"""

import json
import re

from ..source_metadata import META_TYPE, LoadImageWithMetadata

CATEGORY = "image/metadata"

# Input names that hold prompt text on text-encode nodes (CLIPTextEncode, SDXL, Flux,
# Qwen/Krea/HiDream style encoders, Impact wildcard encoders, ...).
_TEXT_KEYS = (
    "text", "prompt", "text_g", "text_l", "clip_l", "t5xxl", "llama", "clip_g",
    "positive", "populated_text", "wildcard_text",
)
# Input names on plain string / primitive / concat nodes.
_STRING_KEYS = (
    "string", "value", "text", "prompt", "string_a", "string_b", "string_c", "string_d",
    "text_a", "text_b", "text_c", "text_d", "text1", "text2", "text3", "text4",
    "populated_text", "wildcard_text",
)
_CONCAT_HINTS = ("concat", "join", "combine", "append")

# LLM / prompt-enhancer nodes. Their OUTPUT (the expanded prompt) is never saved in the
# API graph, only their inputs (instruction template + your text), so they need special
# handling or the extractor returns the system prompt.
_GENERATOR_HINTS = (
    "generate", "llm", "enhance", "expand", "ollama", "gemini", "openai", "gpt",
    "lmstudio", "chat", "florence", "joycaption", "vlm", "rewrite", "promptgen",
)
_SYSTEM_KEYS = (
    "system_prompt", "system", "system_message", "instruction", "instructions",
    "template", "prefix",
)
_USER_KEYS = (
    "user_prompt", "user_input", "user_text", "prompt", "text", "input", "string",
    "caption", "query", "question",
)
# Display nodes whose saved widget holds the text an LLM node produced.
_DISPLAY_HINTS = ("show", "preview", "display", "debug", "view")

# "User's Input:" style markers that end an instruction template.
_USER_MARKER_RE = re.compile(
    r"^\s*(?:\*\*)?(?:the\s+)?user(?:'s|s)?\s+(?:input|prompt|request|caption|text)"
    r"(?:\*\*)?\s*:\s*(?:\*\*)?\s*",
    re.IGNORECASE | re.MULTILINE,
)
# Phrases that only show up in instruction templates, never in a real image prompt.
_TEMPLATE_HINT_RE = re.compile(
    r"(you are an? (?:expert|helpful|professional)|expand the user|"
    r"prompt engineer|follow these rules|output a single)",
    re.IGNORECASE,
)


def _is_link(v):
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], (str, int))


def _strip_template(text):
    """If text is an LLM instruction template with the user's prompt appended, return
    just the user's prompt. Anything else comes back unchanged."""
    if not text:
        return text
    marks = list(_USER_MARKER_RE.finditer(text))
    if marks:
        tail = text[marks[-1].end():].strip()
        if tail:
            return tail
    return text


def _looks_like_template(text):
    return bool(text) and bool(_TEMPLATE_HINT_RE.search(text) or _USER_MARKER_RE.search(text))


def _is_generator(node):
    cls = node.get("class_type", "").lower()
    if any(h in cls for h in _GENERATOR_HINTS):
        return True
    inputs = node.get("inputs", {})
    return any(k in inputs for k in _SYSTEM_KEYS) and any(k in inputs for k in _USER_KEYS)


# --------------------------------------------------------------------------- workflow chunk

def _flatten_strings(v):
    if isinstance(v, str):
        return [v]
    if isinstance(v, (list, tuple)):
        out = []
        for x in v:
            out.extend(_flatten_strings(x))
        return out
    if isinstance(v, dict):
        out = []
        for x in v.values():
            out.extend(_flatten_strings(x))
        return out
    return []


def _workflow_index(workflow):
    """(nodes_by_id, out_links) across the main graph and any subgraphs.
    out_links maps origin node id -> list of target node ids."""
    nodes, out_links = {}, {}
    if not isinstance(workflow, dict):
        return nodes, out_links

    def add_graph(g):
        for n in g.get("nodes", []) or []:
            if isinstance(n, dict) and "id" in n:
                nodes.setdefault(str(n["id"]), n)
        for l in g.get("links", []) or []:
            if isinstance(l, list) and len(l) >= 4:
                src, dst = l[1], l[3]
            elif isinstance(l, dict):
                src, dst = l.get("origin_id"), l.get("target_id")
            else:
                continue
            out_links.setdefault(str(src), []).append(str(dst))

    add_graph(workflow)
    for sg in (workflow.get("definitions", {}) or {}).get("subgraphs", []) or []:
        if isinstance(sg, dict):
            add_graph(sg)
    return nodes, out_links


def _generated_text(ctx, nid):
    """Text an LLM node produced, if a Show Text / Preview node saved it in the workflow."""
    nodes, out_links = ctx.get("wf_index", ({}, {}))
    key = nid.split(":")[-1]  # subgraph ids look like "5:12"
    best = ""
    for dst in out_links.get(key, []):
        node = nodes.get(dst)
        if not node:
            continue
        ntype = str(node.get("type", "")).lower()
        if not any(h in ntype for h in _DISPLAY_HINTS):
            continue
        for s in _flatten_strings(node.get("widgets_values")):
            if len(s.strip()) > len(best) and not _looks_like_template(s):
                best = s.strip()
    return best


# --------------------------------------------------------------------------- ComfyUI graph

def _resolve_generator(graph, nid, node, seen, ctx):
    """Best text for an LLM node: its saved output if any, else the user's own input."""
    out = _generated_text(ctx, nid)
    if out:
        ctx["note"] = "llm output"
        return out
    inputs = node.get("inputs", {})
    for key in _USER_KEYS:
        if key in inputs and key not in _SYSTEM_KEYS:
            s = _resolve_string(graph, inputs[key], seen, ctx)
            if s and s.strip():
                ctx["note"] = "llm input"
                return _strip_template(s).strip()
    return ""


def _resolve_string(graph, value, seen, ctx=None):
    """Turn an input value (literal or link) into a string, following string nodes."""
    ctx = ctx if ctx is not None else {}
    if isinstance(value, str):
        return value
    if not _is_link(value):
        return ""
    nid = str(value[0])
    if nid in seen or nid not in graph:
        return ""
    seen = seen | {nid}
    node = graph[nid]
    inputs = node.get("inputs", {})
    cls = node.get("class_type", "").lower()

    if _is_generator(node):
        return _resolve_generator(graph, nid, node, seen, ctx)

    # Impact wildcard encoders: "populated_text" is the actual text used.
    if inputs.get("populated_text"):
        return _resolve_string(graph, inputs["populated_text"], seen, ctx)

    parts = []
    for key in _STRING_KEYS:
        if key in inputs:
            s = _resolve_string(graph, inputs[key], seen, ctx)
            if s:
                parts.append(s)
                if not any(h in cls for h in _CONCAT_HINTS):
                    break  # plain string node: first hit is the value
    if any(h in cls for h in _CONCAT_HINTS):
        delim = inputs.get("delimiter", inputs.get("separator", ", "))
        delim = delim if isinstance(delim, str) else ", "
        return delim.join(parts)
    return parts[0] if parts else ""


def _texts_from_conditioning(graph, link, seen=frozenset(), ctx=None):
    """Walk a CONDITIONING link upstream and collect the prompt text that fed it."""
    ctx = ctx if ctx is not None else {}
    if not _is_link(link):
        return []
    nid = str(link[0])
    if nid in seen or nid not in graph:
        return []
    seen = seen | {nid}
    node = graph[nid]
    inputs = node.get("inputs", {})
    cls = node.get("class_type", "")

    if "zeroout" in cls.lower():
        return []  # ConditioningZeroOut = deliberately empty negative

    # Text encoder: any node with a text-ish input that resolves to a string.
    found = []
    for key in _TEXT_KEYS:
        if key in inputs and key != "positive":
            s = _resolve_string(graph, inputs[key], seen, ctx)
            if s and s.strip() and s.strip() not in found:
                found.append(s.strip())
    if found:
        # SDXL-style encoders often repeat one prompt in text_g/text_l: keep it once.
        return [found[0]] if _same_prompt(found) else ["\n".join(found)]

    # Otherwise keep walking up every linked input (combine / concat / set-area / ControlNet ...).
    out = []
    for key, val in inputs.items():
        if _is_link(val):
            for t in _texts_from_conditioning(graph, val, seen, ctx):
                if t not in out:
                    out.append(t)
    return out


def _same_prompt(texts):
    """True when all collected texts are identical (e.g. SDXL text_g == text_l)."""
    return len(set(texts)) == 1


def _sampler_candidates(graph):
    """Nodes that consume positive/negative conditioning, best guesses first."""
    def key(item):
        nid, node = item
        cls = node.get("class_type", "").lower()
        rank = 0 if "ksampler" in cls else 1 if ("sampler" in cls or "guider" in cls) else 2
        try:
            n = int(nid.split(":")[-1])
        except ValueError:
            n = 0
        return (rank, n)

    out = []
    for nid, node in sorted(graph.items(), key=key):
        inputs = node.get("inputs", {})
        if _is_link(inputs.get("positive")):
            out.append((inputs.get("positive"), inputs.get("negative")))
        elif _is_link(inputs.get("conditioning")) and "guider" in node.get("class_type", "").lower():
            out.append((inputs.get("conditioning"), None))  # BasicGuider (Flux etc.): no negative
    return out


def _load_json(v):
    try:
        return json.loads(v) if isinstance(v, str) else v
    except Exception:
        return None


def parse_comfy_prompt(prompt_json, workflow_json=None):
    """Return (positive, negative, note) or None. note is "" or "llm output"/"llm input"."""
    graph = _load_json(prompt_json)
    if not isinstance(graph, dict):
        return None
    graph = {str(k): v for k, v in graph.items() if isinstance(v, dict)}
    ctx = {"wf_index": _workflow_index(_load_json(workflow_json))}

    for pos_link, neg_link in _sampler_candidates(graph):
        pos = _texts_from_conditioning(graph, pos_link, ctx=ctx)
        if pos:
            neg = _texts_from_conditioning(graph, neg_link, ctx=ctx) if neg_link else []
            pos_s, neg_s = "\n".join(pos), "\n".join(neg)
            # Safety net for enhancer nodes we didn't recognise by name.
            if _looks_like_template(pos_s):
                stripped = _strip_template(pos_s)
                if stripped != pos_s:
                    pos_s, ctx["note"] = stripped, "llm input"
            return pos_s, neg_s, ctx.get("note", "")
    return None


# --------------------------------------------------------------------------- A1111 / Civitai

_NEG_RE = re.compile(r"^\s*Negative prompt:\s?", re.MULTILINE)
_SETTINGS_RE = re.compile(r"^\s*Steps:\s*\d+.*$", re.MULTILINE)


def parse_a1111_parameters(text):
    if not text or not text.strip():
        return None
    settings = _SETTINGS_RE.search(text)
    body = text[:settings.start()] if settings else text
    neg = _NEG_RE.search(body)
    if neg:
        return body[:neg.start()].strip(), body[neg.end():].strip()
    return body.strip(), ""


# --------------------------------------------------------------------------- dispatcher

def extract_prompts(meta):
    """Return (positive, negative, source) from an IMAGE_META dict."""
    text = (meta or {}).get("text", {}) or {}

    if "prompt" in text:
        r = parse_comfy_prompt(text["prompt"], text.get("workflow"))
        if r:
            src = "comfyui" + (f" ({r[2]})" if r[2] else "")
            return r[0], r[1], src
    if "parameters" in text:
        r = parse_a1111_parameters(text["parameters"])
        if r:
            return r[0], r[1], "a1111"
    # Some tools store plain fields
    pos = text.get("positive") or text.get("Description") or ""
    neg = text.get("negative") or text.get("negative_prompt") or ""
    if pos or neg:
        return pos.strip(), neg.strip(), "plain"
    return "", "", "none"


def _log(source, path, pos, neg):
    name = (path or "").replace("\\", "/").split("/")[-1]
    if source == "none":
        print(f"[PromptExtract] {name}: no prompt found in metadata")
    else:
        print(f"[PromptExtract] {name}: {source} prompt ({len(pos)} chars +, {len(neg)} chars -)")


# --------------------------------------------------------------------------- nodes

class LoadImageExtractPrompts(LoadImageWithMetadata):
    """Load Image that also outputs the positive and negative prompt baked into the file."""

    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "STRING", META_TYPE, "STRING")
    RETURN_NAMES = ("image", "mask", "positive", "negative", "source_metadata", "filename")
    OUTPUT_TOOLTIPS = (
        None, None,
        "Positive prompt read from the image's metadata",
        "Negative prompt read from the image's metadata (empty if there wasn't one)",
        "Wire into Save Image (Source Metadata) to keep the original workflow",
        "File name without extension",
    )
    FUNCTION = "load_prompts"
    CATEGORY = CATEGORY

    def load_prompts(self, image):
        img, mask, meta, name, _name_ext, path = self.load(image)
        pos, neg, source = extract_prompts(meta)
        _log(source, path, pos, neg)
        return (img, mask, pos, neg, meta, name)


class ExtractPromptsFromMetadata:
    """Positive/negative prompts from a source_metadata link."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"source_metadata": (META_TYPE,)}}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("positive", "negative")
    FUNCTION = "extract"
    CATEGORY = CATEGORY

    def extract(self, source_metadata):
        pos, neg, source = extract_prompts(source_metadata)
        _log(source, (source_metadata or {}).get("source"), pos, neg)
        return (pos, neg)


NODE_CLASS_MAPPINGS = {
    "BertsLoadImageExtractPrompts": LoadImageExtractPrompts,
    "BertsExtractPromptsFromMetadata": ExtractPromptsFromMetadata,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "BertsLoadImageExtractPrompts": "Load Image (Extract Prompts)",
    "BertsExtractPromptsFromMetadata": "Extract Prompts (Metadata)",
}
