# Aspect Ratio Passthrough

A small ComfyUI custom node. It reads the aspect ratio directly off an input
image and combines it with a megapixel target you choose, so downstream
generation matches your source image's shape without you manually looking up
or typing in an aspect ratio.

Like the built-in Resolution Selector node, but the aspect ratio comes from
a wired-in image instead of a preset dropdown.

## Install

1. Copy this whole folder into your ComfyUI `custom_nodes` directory, so you
   end up with:
   `ComfyUI/custom_nodes/ComfyUI-AspectRatioPassthrough/`
2. Restart ComfyUI.
3. The node appears in the node search / right-click menu as
   **Aspect Ratio Passthrough**, under the `utils/resolution` category.

No extra dependencies — it only uses Python's standard library `math`.

## Inputs

- **image** (`IMAGE`) — the image to read the aspect ratio from (e.g. straight
  out of a `LoadImage` node, or any reference image already in your graph).
- **megapixels** (`FLOAT`, default 1.0) — target total resolution.
- **multiple_of** (`INT`, default 64) — rounds output width/height to the
  nearest multiple of this value (most diffusion/video models want 8, 16, 32,
  or 64-aligned dimensions).

## Outputs

- **width** (`INT`) — computed width in pixels, aligned to `multiple_of`.
- **height** (`INT`) — computed height in pixels, aligned to `multiple_of`.
- **aspect_ratio** (`FLOAT`) — raw `width / height` of the *source* image
  (e.g. `1.7778` for 16:9), for wiring into math/logic nodes downstream.
- **aspect_ratio_string** (`STRING`) — simplified ratio as text (e.g.
  `"16:9"`), handy for labels, filenames, or display widgets.
- **megapixels** (`FLOAT`) — the *actual* megapixel count of the rounded
  width/height (slightly different from your requested value once rounded to
  `multiple_of`).

## Example wiring

```
LoadImage ──► image ──┐
                       ├─► [Aspect Ratio Passthrough] ─► width  ──► Empty Latent Image (width)
        megapixels ────┘                              ─► height ──► Empty Latent Image (height)
                                                        ─► aspect_ratio_string ─► (e.g. Show Text node)
```

Connect `width` and `height` directly into any node's INT inputs (right-click
the target widget → "Convert widget to input" first if it's not already
exposed as a socket).

## Notes

- Width and height are rounded independently to the nearest `multiple_of`,
  which can shift the output aspect ratio very slightly from the source
  image's exact ratio — this is the same trade-off other resolution-bucket
  nodes make, and keeps dimensions compatible with the models you feed them
  into.
- If you need the *unrounded* aspect ratio for something else, that's what
  the `aspect_ratio` float output is for (it's computed from the source
  image before any rounding).
