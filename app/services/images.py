"""Upload validation and image-quality checks.

* The upload is read in chunks and aborted as soon as it exceeds the size limit.
* The file type is decided by decoding it (Pillow), never by the client's Content-Type / name.
* Decompression bombs are refused (pixel limit).
* The stored copy is re-encoded as JPEG, which drops EXIF metadata (including GPS position).
"""
from __future__ import annotations

import hashlib
import io

import numpy as np
from fastapi import UploadFile
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

from ..config import MAX_IMAGE_PIXELS, MAX_UPLOAD_MB
from ..core.errors import AppError

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
ALLOWED = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "MPO": "image/jpeg"}
MIN_SIDE = 128
STORE_MAX_SIDE = 1600


async def read_upload(file: UploadFile) -> bytes:
    limit = MAX_UPLOAD_MB * 1024 * 1024
    buf = bytearray()
    while chunk := await file.read(1024 * 256):
        buf += chunk
        if len(buf) > limit:
            raise AppError(413, f"Image is larger than {MAX_UPLOAD_MB} MB. Please choose a smaller photo.")
    if not buf:
        raise AppError(400, "The uploaded file is empty.", "empty_file")
    return bytes(buf)


def decode(data: bytes) -> tuple[Image.Image, str]:
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            probe.verify()                       # structural check (truncated / corrupt files)
        if fmt not in ALLOWED:
            raise AppError(415, "Unsupported image type. Please upload a JPG, PNG or WebP photo.")
        img = Image.open(io.BytesIO(data))
        img.load()
    except Image.DecompressionBombError:
        raise AppError(413, "Image resolution is too large. Please upload a normal photo.")
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise AppError(415, "That file isn't a readable image. Please upload a JPG, PNG or WebP photo.")
    img = ImageOps.exif_transpose(img).convert("RGB")
    if min(img.size) < MIN_SIDE:
        raise AppError(422, f"Image is too small ({img.size[0]}×{img.size[1]} px). Use a photo at least "
                            f"{MIN_SIDE} px on the shorter side.", "image_too_small")
    return img, ALLOWED[fmt]


def quality(img: Image.Image) -> dict:
    """Cheap checks that catch the most common bad photos. Returns warnings, never blocks."""
    g = img.convert("L")
    g.thumbnail((512, 512))
    a = np.asarray(g, dtype=np.float32)
    lap = np.asarray(g.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    sharp = float(lap.var())
    bright = float(a.mean())
    clipped = float(((a < 8) | (a > 247)).mean())
    warnings = []
    if sharp < 60:
        warnings.append({"code": "blurry", "message": "The photo looks blurry — hold the camera steady and tap to focus on the symptoms."})
    if bright < 45:
        warnings.append({"code": "dark", "message": "The photo is quite dark — take it in daylight or move to a brighter spot."})
    if bright > 215 or clipped > 0.35:
        warnings.append({"code": "overexposed", "message": "The photo is very bright or washed out — avoid direct sun on the leaf or the flash."})
    if min(img.size) < 300:
        warnings.append({"code": "low_resolution", "message": "Low resolution — move closer so the leaf fills the frame."})
    return {"sharpness": round(sharp, 1), "brightness": round(bright, 1), "warnings": warnings}


def to_storage_jpeg(img: Image.Image) -> bytes:
    im = img.copy()
    im.thumbnail((STORE_MAX_SIDE, STORE_MAX_SIDE))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88, optimize=True)     # re-encode: no EXIF / GPS carried over
    return buf.getvalue()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
