import math


class AspectRatioPassthrough:
    """
    Reads the aspect ratio straight off an input image and combines it with a
    user-chosen megapixel target to produce ready-to-use width/height values.

    Think of it as "Resolution Selector", but instead of picking the aspect
    ratio from a preset dropdown, it's read automatically from whatever image
    you feed in (e.g. your LoadImage / reference image node), so downstream
    generation matches the source image's shape at whatever megapixel budget
    you want.
    """

    CATEGORY = "utils/resolution"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "megapixels": (
                    "FLOAT",
                    {
                        "default": 1.0,
                        "min": 0.01,
                        "max": 64.0,
                        "step": 0.01,
                        "tooltip": "Target total resolution, in megapixels.",
                    },
                ),
                "multiple_of": (
                    "INT",
                    {
                        "default": 64,
                        "min": 1,
                        "max": 256,
                        "step": 1,
                        "tooltip": "Round width/height to the nearest multiple of this "
                        "(most diffusion models want 8, 16, 32 or 64).",
                    },
                ),
            }
        }

    RETURN_TYPES = ("INT", "INT", "FLOAT", "STRING", "FLOAT")
    RETURN_NAMES = ("width", "height", "aspect_ratio", "aspect_ratio_string", "megapixels")
    FUNCTION = "compute"
    CATEGORY = "utils/resolution"

    @staticmethod
    def _round_to_multiple(value, multiple):
        if multiple <= 1:
            return max(1, int(round(value)))
        rounded = int(round(value / multiple)) * multiple
        return max(multiple, rounded)

    def compute(self, image, megapixels, multiple_of):
        # ComfyUI IMAGE tensors are [batch, height, width, channels]
        _, src_h, src_w, _ = image.shape
        src_h = int(src_h)
        src_w = int(src_w)

        aspect_ratio = src_w / src_h

        # Solve width * height = target_pixels while keeping width/height == aspect_ratio
        target_pixels = float(megapixels) * 1_000_000.0
        raw_height = math.sqrt(target_pixels / aspect_ratio)
        raw_width = aspect_ratio * raw_height

        width = self._round_to_multiple(raw_width, multiple_of)
        height = self._round_to_multiple(raw_height, multiple_of)

        actual_megapixels = (width * height) / 1_000_000.0

        gcd = math.gcd(src_w, src_h)
        aspect_ratio_string = f"{src_w // gcd}:{src_h // gcd}"

        return (width, height, aspect_ratio, aspect_ratio_string, actual_megapixels)


NODE_CLASS_MAPPINGS = {
    "AspectRatioPassthrough": AspectRatioPassthrough,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "AspectRatioPassthrough": "Aspect Ratio Passthrough",
}
