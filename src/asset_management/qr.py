"""Deterministic public-safe QR identity helpers."""

from __future__ import annotations

import base64
from io import BytesIO
from uuid import NAMESPACE_URL, UUID, uuid5

import qrcode
from qrcode.image.svg import SvgPathImage


def asset_qr_token(asset_id: str) -> UUID:
    """Return the stable opaque lookup token for one stable asset identifier."""

    return uuid5(NAMESPACE_URL, f"ai-maintenance-copilot:asset:{asset_id}")


def qr_svg_base64(payload: str) -> str:
    """Render a compact SVG QR code and return base64 without a data-URL prefix."""

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(image_factory=SvgPathImage)
    output = BytesIO()
    image.save(output)
    return base64.b64encode(output.getvalue()).decode("ascii")
