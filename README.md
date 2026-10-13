# Bert's Tools

A small pack of ComfyUI custom nodes.

| Node | Category | What it does |
|---|---|---|
| **Aspect Ratio Passthrough** | `utils/resolution` | Reads the aspect ratio off an input image and turns it into width/height at a megapixel target you choose. |
| **Load Image (Keep Metadata)** | `image/metadata` | Drop-in Load Image that also outputs the file's generation metadata and filename. |
| **Read Image Metadata (Path)** | `image/metadata` | Reads generation metadata from any file path (for batch / folder loaders). |
| **Save Image (Source Metadata)** | `image/metadata` | Saves PNGs that carry the *source* image's metadata, so detailed/upscaled results still load the original workflow. |

Full docs for each node:

- [Aspect Ratio Passthrough](aspect_ratio_passthrough/README.md)
- [Source Metadata](source_metadata/README.md)

## Installation

Clone into your ComfyUI `custom_nodes` folder and restart ComfyUI:

```
cd ComfyUI/custom_nodes
git clone https://github.com/robandiz25/comfyui-berts-tools.git
```

No extra dependencies — only Python's standard library plus Pillow, numpy and torch,
which ComfyUI already includes.

### Upgrading from the standalone repos

These nodes used to live in
[ComfyUI-AspectRatioPassthrough](https://github.com/robandiz25/ComfyUI-AspectRatioPassthrough) and
[comfyui-source-metadata](https://github.com/robandiz25/comfyui-source-metadata).
Node IDs haven't changed, so saved workflows load as before. **Delete the old
`ComfyUI-AspectRatioPassthrough` and `comfyui-source-metadata` folders from `custom_nodes`**
before installing this pack, or ComfyUI will register the same nodes twice.

## License

MIT — see [LICENSE](LICENSE).
