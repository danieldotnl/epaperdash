"""Photo -> Spectra 6 dithered PNG, for the colour reTerminal E1002 panel.

Wraps the MIT-licensed `epaper-dithering` package (Rust core): it dithers against
the panel's *measured* 6-colour palette using OKLab perceptual matching plus auto
tone/gamut compression — far better for photos than snapping each pixel to the
nearest idealised primary. We own only the framing to the 800x480 panel size.
"""

from io import BytesIO

import epaper_dithering as ed
from PIL import Image, ImageOps

WIDTH, HEIGHT = 800, 480

# Measured Spectra 6 anchors (the muted RGBs the panel actually shows). If the
# device's own nearest-colour pass mismaps these, swap for the idealised
# `ed.ColorScheme.BWGBRY` (pure primaries) — the rest of the call is unchanged.
PALETTE = ed.SPECTRA_7_3_6COLOR_V2
MODE = ed.DitherMode.FLOYD_STEINBERG


def dither(image_bytes: bytes, *, fit: str = "cover") -> bytes:
    """Frame an image to 800x480 and dither it to the Spectra 6 palette.

    fit="cover" scales to fill then centre-crops (the photo-frame default);
    fit="contain" fits the whole image and letterboxes the remainder on white.
    """
    src = ImageOps.exif_transpose(Image.open(BytesIO(image_bytes))).convert("RGB")
    if fit == "contain":
        framed = ImageOps.pad(src, (WIDTH, HEIGHT), color=(255, 255, 255))
    else:
        framed = ImageOps.fit(src, (WIDTH, HEIGHT))

    out = ed.dither_image(framed, PALETTE, mode=MODE, tone="auto", gamut="auto")

    buf = BytesIO()
    out.convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()
