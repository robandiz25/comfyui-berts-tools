"""
Bert's Tools - a small pack of ComfyUI custom nodes by robandiz25.

  * Aspect Ratio Passthrough       (utils/resolution)
  * Load Image (Keep Metadata)     (image/metadata)
  * Read Image Metadata (Path)     (image/metadata)
  * Save Image (Source Metadata)   (image/metadata)

Node IDs are unchanged from the original standalone repos, so existing
workflows keep working. Uninstall the old standalone packs first to avoid
duplicate-node warnings.
"""

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}


def _merge(name, module_path):
    try:
        import importlib
        mod = importlib.import_module(module_path, package=__name__)
    except Exception as e:  # one broken node shouldn't take down the whole pack
        print(f"[Bert's Tools] Failed to load {name}: {e}")
        return
    NODE_CLASS_MAPPINGS.update(getattr(mod, "NODE_CLASS_MAPPINGS", {}))
    NODE_DISPLAY_NAME_MAPPINGS.update(getattr(mod, "NODE_DISPLAY_NAME_MAPPINGS", {}))


_merge("Aspect Ratio Passthrough", ".aspect_ratio_passthrough")
_merge("Source Metadata", ".source_metadata")

print(f"[Bert's Tools] Loaded {len(NODE_CLASS_MAPPINGS)} nodes")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
