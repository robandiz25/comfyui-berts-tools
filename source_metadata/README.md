# ComfyUI Source Metadata

Keep the original generation metadata when you detail or upscale an image in ComfyUI.

A detailer → upscale workflow normally saves its output with *its own* workflow embedded, so the
prompt, seed, LoRAs and workflow from the image you started with are lost. These nodes read the
metadata from the source image and write it into the final PNG, so dragging the upscaled result
back into ComfyUI loads the **original** generation workflow.

## Nodes

All nodes are under **image/metadata**.

| Node | What it does |
|---|---|
| **Load Image (Keep Metadata)** | Drop-in replacement for Load Image. Outputs `image`, `mask`, `source_metadata`, plus `filename` (no extension), `filename_ext` and `full_path`. |
| **Read Image Metadata (Path)** | Reads metadata from any file path string — use it with batch or folder loaders. |
| **Save Image (Source Metadata)** | Saves PNGs carrying the source image's metadata instead of this workflow's. |

## Usage

1. Replace your **Load Image** with **Load Image (Keep Metadata)**.
2. Run the image through your detailer / upscaler as usual.
3. Replace the final **Save Image** with **Save Image (Source Metadata)**, connecting the upscaled
   image to `images` and the loader's `source_metadata` output straight to it.
4. Optional: connect the loader's `filename` output (via a text concatenate node if you want a
   suffix) to `filename_prefix` to name outputs after the original file.

### Save options

- **keep_this_workflow** (default on): also stores the detailer/upscale workflow under separate
  `upscale_prompt` / `upscale_workflow` keys. It never replaces the original metadata.
- If the source image has no metadata, the node saves like the stock Save Image.
- `filename_prefix` supports `%date:yyyy-MM-dd%` (tokens: yyyy, yy, MM, dd, hh, mm, ss), `%date%`,
  `%year%`, `%month%`, `%day%`, `%hour%`, `%minute%`, `%second%` — expanded by the node itself, so
  they work even when the prefix comes in through a link.

## Supported source formats

- **PNG** text chunks: ComfyUI `prompt` / `workflow`, A1111 / Civitai `parameters`, and any other keys
- **JPEG / WebP** EXIF UserComment (A1111 / Civitai)
- **WebP** saved by ComfyUI (EXIF `prompt:` / `workflow:` tags)

Output is always PNG.

## Installation

Part of [Bert's Tools](../README.md) — see the main README for install steps.

## License

MIT — see [LICENSE](../LICENSE).
