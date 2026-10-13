"""
ComfyUI Source Metadata
-----------------------
Carries the generation metadata from an input image through a workflow
(e.g. detailer -> DLSS5 upscale) and writes it into the final saved PNG,
the same job image_meta_swap.py does by hand.

Nodes:
  * Load Image (Keep Metadata)        - drop-in Load Image that also outputs the file's metadata
  * Read Image Metadata (Path)        - metadata from any file path (for batch / folder loaders)
  * Save Image (Source Metadata)      - saves PNGs carrying the source image's metadata

Reads: PNG text chunks (ComfyUI prompt/workflow, A1111/Civitai parameters, anything else),
       JPEG/WebP EXIF UserComment (A1111/Civitai), ComfyUI WebP EXIF "prompt:"/"workflow:" tags.
Writes: PNG text chunks, so dragging the result into ComfyUI loads the ORIGINAL workflow.

No extra pip installs: uses only Pillow, numpy and torch, which ComfyUI already has.
"""

import datetime
import hashlib
import json
import os
import re

import numpy as np
import torch
from PIL import Image, ImageOps
from PIL.PngImagePlugin import PngInfo

import folder_paths

CATEGORY = "image/metadata"
META_TYPE = "IMAGE_META"

_EXIF_IFD = 0x8769
_USER_COMMENT = 0x9286


# --------------------------------------------------------------------------- helpers

def _decode_user_comment(raw):
    """Decode an EXIF UserComment (A1111 / Civitai store 'parameters' here)."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.replace("\x00", "").strip()
    head, body = raw[:8], raw[8:]
    if head.startswith(b"UNICODE"):
        best, best_score = "", -1
        for enc in ("utf-16-be", "utf-16-le"):
            try:
                s = body.decode(enc)
            except UnicodeDecodeError:
                continue
            score = sum(1 for c in s if ord(c) < 128)
            if score > best_score:
                best, best_score = s, score
        text = best
    elif head.startswith(b"ASCII"):
        text = body.decode("ascii", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")
    return text.replace("\x00", "").strip()


def read_source_metadata(path):
    """Return {key: text} for every piece of generation metadata found in the file."""
    meta = {}
    try:
        with Image.open(path) as img:
            # PNG tEXt / iTXt / zTXt chunks
            text = getattr(img, "text", None)
            if text:
                for k, v in text.items():
                    meta[str(k)] = str(v)

            # EXIF (JPEG / WebP)
            try:
                exif = img.getexif()
            except Exception:
                exif = None
            if exif:
                # ComfyUI WebP saves: tag 0x0110 = "prompt:{...}", 0x010F = "workflow:{...}"
                for _tag, val in exif.items():
                    if isinstance(val, bytes):
                        try:
                            val = val.decode("utf-8")
                        except UnicodeDecodeError:
                            continue
                    if isinstance(val, str) and ":" in val:
                        key, rest = val.split(":", 1)
                        if key.isidentifier() and rest.lstrip()[:1] in ("{", "["):
                            meta.setdefault(key, rest.strip().rstrip("\x00"))
                # A1111 / Civitai: Exif UserComment
                try:
                    uc = exif.get_ifd(_EXIF_IFD).get(_USER_COMMENT)
                except Exception:
                    uc = None
                comment = _decode_user_comment(uc)
                if comment:
                    meta.setdefault("parameters", comment)
    except Exception as e:
        print(f"[SourceMetadata] Could not read metadata from {path}: {e}")
    return meta


def _make_meta(path):
    text = read_source_metadata(path)
    keys = ", ".join(sorted(text)) or "none"
    print(f"[SourceMetadata] {os.path.basename(path)}: found {keys}")
    return {"text": text, "source": path}


def _file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_DATE_TOKENS = [  # longest first, same tokens as the ComfyUI frontend
    ("yyyy", "%Y"), ("yy", "%y"), ("MM", "%m"), ("M", "{M}"), ("dd", "%d"), ("d", "{d}"),
    ("hh", "%H"), ("h", "{h}"), ("mm", "%M"), ("m", "{m}"), ("ss", "%S"), ("s", "{s}"),
]
_DATE_RE = re.compile(r"%date(?::([^%]*))?%")
_TOKEN_RE = re.compile("|".join(t for t, _ in _DATE_TOKENS))


def _expand_date(match, now):
    fmt = match.group(1) or "yyyy-MM-dd"
    lookup = dict(_DATE_TOKENS)
    short = {"{M}": str(now.month), "{d}": str(now.day), "{h}": str(now.hour),
             "{m}": str(now.minute), "{s}": str(now.second)}

    def tok(m):
        code = lookup[m.group(0)]
        return short.get(code) or now.strftime(code)
    return _TOKEN_RE.sub(tok, fmt)


def expand_prefix(prefix):
    """Expand %date:...% tokens when the frontend didn't (e.g. prefix arrived via a link)."""
    now = datetime.datetime.now()
    out = _DATE_RE.sub(lambda m: _expand_date(m, now), prefix)
    out = out.replace("%year%", f"{now.year}").replace("%month%", f"{now.month:02}") \
             .replace("%day%", f"{now.day:02}").replace("%hour%", f"{now.hour:02}") \
             .replace("%minute%", f"{now.minute:02}").replace("%second%", f"{now.second:02}")
    # Strip characters Windows can't use in a path (keep / and \ as folder separators)
    return re.sub(r'[<>:"|?*\x00-\x1f]', "_", out)


# --------------------------------------------------------------------------- nodes

class LoadImageWithMetadata:
    """Same as the stock Load Image, plus a metadata output."""

    @classmethod
    def INPUT_TYPES(cls):
        input_dir = folder_paths.get_input_directory()
        files = [f for f in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, f))]
        try:
            files = folder_paths.filter_files_content_types(files, ["image"])
        except Exception:
            pass
        return {"required": {"image": (sorted(files), {"image_upload": True})}}

    RETURN_TYPES = ("IMAGE", "MASK", META_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "mask", "source_metadata", "filename", "filename_ext", "full_path")
    OUTPUT_TOOLTIPS = (
        None, None, None,
        "File name without extension, e.g. 'my_image' - wire into a save node's filename_prefix",
        "File name with extension, e.g. 'my_image.png'",
        "Absolute path to the source file",
    )
    FUNCTION = "load"
    CATEGORY = CATEGORY

    def load(self, image):
        path = os.path.abspath(folder_paths.get_annotated_filepath(image))
        meta = _make_meta(path)
        name_ext = os.path.basename(path)
        name = os.path.splitext(name_ext)[0]

        img = Image.open(path)
        img = ImageOps.exif_transpose(img)
        if img.mode == "I":
            img = img.point(lambda i: i * (1 / 255))
        rgb = np.array(img.convert("RGB")).astype(np.float32) / 255.0
        image_t = torch.from_numpy(rgb)[None,]

        if "A" in img.getbands():
            a = np.array(img.getchannel("A")).astype(np.float32) / 255.0
            mask = 1.0 - torch.from_numpy(a)
        else:
            mask = torch.zeros((64, 64), dtype=torch.float32)
        return (image_t, mask.unsqueeze(0), meta, name, name_ext, path)

    @classmethod
    def IS_CHANGED(cls, image):
        return _file_hash(folder_paths.get_annotated_filepath(image))

    @classmethod
    def VALIDATE_INPUTS(cls, image):
        if not folder_paths.exists_annotated_filepath(image):
            return f"Invalid image file: {image}"
        return True


class ReadImageMetadataFromPath:
    """Metadata from a file path - wire a batch/folder loader's filename output here."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"path": ("STRING", {"default": "", "multiline": False})}}

    RETURN_TYPES = (META_TYPE,)
    RETURN_NAMES = ("source_metadata",)
    FUNCTION = "read"
    CATEGORY = CATEGORY

    def read(self, path):
        path = path.strip().strip('"')
        if not os.path.isfile(path):
            raise FileNotFoundError(f"[SourceMetadata] File not found: {path}")
        return (_make_meta(path),)

    @classmethod
    def IS_CHANGED(cls, path):
        path = path.strip().strip('"')
        return _file_hash(path) if os.path.isfile(path) else path


class SaveImageWithSourceMetadata:
    """Save PNGs that carry the source image's metadata instead of this workflow's."""

    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"
        self.compress_level = 4

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "source_metadata": (META_TYPE,),
                "filename_prefix": ("STRING", {"default": "ComfyUI_detailed"}),
                "keep_this_workflow": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Also store this detailer/upscale workflow under separate keys "
                               "(upscale_prompt / upscale_workflow). It never replaces the original.",
                }),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    RETURN_TYPES = ()
    FUNCTION = "save"
    OUTPUT_NODE = True
    CATEGORY = CATEGORY

    def save(self, images, source_metadata, filename_prefix="ComfyUI_detailed",
             keep_this_workflow=True, prompt=None, extra_pnginfo=None):
        src = dict((source_metadata or {}).get("text", {}))
        if not src:
            print("[SourceMetadata] Source image had no metadata; saving this workflow's instead.")

        filename_prefix = expand_prefix(filename_prefix)
        full_folder, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(
            filename_prefix, self.output_dir, images[0].shape[1], images[0].shape[0])

        results = []
        for batch_number, image in enumerate(images):
            arr = np.clip(255.0 * image.cpu().numpy(), 0, 255).astype(np.uint8)
            img = Image.fromarray(arr)

            info = PngInfo()
            if src:
                for k, v in src.items():
                    info.add_text(k, v)
                if keep_this_workflow:
                    if prompt is not None:
                        info.add_text("upscale_prompt", json.dumps(prompt))
                    for k, v in (extra_pnginfo or {}).items():
                        info.add_text(f"upscale_{k}", json.dumps(v))
            else:
                # Nothing to carry over: behave like the stock Save Image.
                if prompt is not None:
                    info.add_text("prompt", json.dumps(prompt))
                for k, v in (extra_pnginfo or {}).items():
                    info.add_text(k, json.dumps(v))

            name = filename.replace("%batch_num%", str(batch_number))
            file = f"{name}_{counter:05}_.png"
            img.save(os.path.join(full_folder, file), pnginfo=info, compress_level=self.compress_level)
            results.append({"filename": file, "subfolder": subfolder, "type": self.type})
            counter += 1

        return {"ui": {"images": results}}


NODE_CLASS_MAPPINGS = {
    "LoadImageWithMetadata": LoadImageWithMetadata,
    "ReadImageMetadataFromPath": ReadImageMetadataFromPath,
    "SaveImageWithSourceMetadata": SaveImageWithSourceMetadata,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoadImageWithMetadata": "Load Image (Keep Metadata)",
    "ReadImageMetadataFromPath": "Read Image Metadata (Path)",
    "SaveImageWithSourceMetadata": "Save Image (Source Metadata)",
}
