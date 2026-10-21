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


def _is_link(v):
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], (str, int))


# --------------------------------------------------------------------------- ComfyUI graph

def _resolve_string(graph, value, seen):
    """Turn an input value (literal or link) into a string, following string nodes."""
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

    # Impact wildcard encoders: "populated_text" is the actual text used.
    if inputs.get("populated_text"):
        return _resolve_string(graph, inputs["populated_text"], seen)

    parts = []
    for key in _STRING_KEYS:
        if key in inputs:
            s = _resolve_string(graph, inputs[key], seen)
            if s:
                parts.append(s)
                if not any(h in cls for h in _CONCAT_HINTS):
                    break  # plain string node: first hit is the value
    if any(h in cls for h in _CONCAT_HINTS):
        delim = inputs.get("delimiter", inputs.get("separator", ", "))
        delim = delim if isinstance(delim, str) else ", "
        return delim.join(parts)
    return parts[0] if parts else ""


def _texts_from_conditioning(graph, link, seen=frozenset()):
    """Walk a CONDITIONING link upstream and collect the prompt text that fed it."""
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
            s = _resolve_string(graph, inputs[key], seen)
            if s and s.strip() and s.strip() not in found:
                found.append(s.strip())
    if found:
        # SDXL-style encoders often repeat one prompt in text_g/text_l: keep it once.
        return [found[0]] if _same_prompt(found) else ["\n".join(found)]

    # Otherwise keep walking up every linked input (combine / concat / set-area / ControlNet ...).
    out = []
    for key, val in inputs.items():
        if _is_link(val):
            for t in _texts_from_conditioning(graph, val, seen):
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


def parse_comfy_prompt(prompt_json):
    try:
        graph = json.loads(prompt_json) if isinstance(prompt_json, str) else prompt_json
    except Exception:
        return None
    if not isinstance(graph, dict):
        return None
    graph = {str(k): v for k, v in graph.items() if isinstance(v, dict)}

    for pos_link, neg_link in _sampler_candidates(graph):
        pos = _texts_from_conditioning(graph, pos_link)
        if pos:
            neg = _texts_from_conditioning(graph, neg_link) if neg_link else []
            return "\n".join(pos), "\n".join(neg)
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
        r = parse_comfy_prompt(text["prompt"])
        if r:
            return r[0], r[1], "comfyui"
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
