"""Read independent RGBA mask channels without browser canvas premultiplication."""
import struct
from .model import ValidationError

MAX_MASK_EDGE=8192
MAX_MASK_PIXELS=16*1024*1024


def read_mask_pixels(path,expected_size):
    from PIL import Image
    if (not isinstance(expected_size,(list,tuple)) or len(expected_size)!=2
            or any(type(value) is not int or not 0<value<=MAX_MASK_EDGE for value in expected_size)
            or expected_size[0]*expected_size[1]>MAX_MASK_PIXELS):
        raise ValidationError("Invalid native mask dimensions.")
    if path.stat().st_size>MAX_MASK_PIXELS*4+1024*1024:
        raise ValidationError("Native mask file exceeds its size limit.")
    with Image.open(path) as image:
        if image.format!="PNG" or image.size!=tuple(expected_size) or image.mode!="RGBA":
            raise ValidationError("Native mask does not match its RGBA render contract.")
        pixels=image.tobytes()
    return struct.pack("<II",*expected_size)+pixels
