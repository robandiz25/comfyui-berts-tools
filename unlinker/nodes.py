"""
Unlinker - a pass-through with a Link / Unlink button.

Wire it between any output (e.g. a QwenVL caption) and any input (e.g. the
text box of a CLIP Text Encode). "Unlink" removes the wire(s) leaving
Unlinker so the target box can be typed in by hand; "Link" restores them.

The wiring is handled in the browser (js/unlinker.js); this side is a plain
pass-through.
"""


class AnyType(str):
    """Wildcard type that matches every other type."""

    def __ne__(self, other):
        return False


ANY = AnyType("*")


class BertsUnlinker:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"value": (ANY, {})}}

    RETURN_TYPES = (ANY,)
    RETURN_NAMES = ("value",)
    FUNCTION = "passthrough"
    CATEGORY = "utils"
    DESCRIPTION = (
        "Pass-through with a Link/Unlink button. Unlink removes the output "
        "wire so the target field can be typed in manually; Link restores it."
    )

    def passthrough(self, value):
        return (value,)


NODE_CLASS_MAPPINGS = {"BertsUnlinker": BertsUnlinker}
NODE_DISPLAY_NAME_MAPPINGS = {"BertsUnlinker": "Unlinker"}
