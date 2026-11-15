"""Server-side camera capture for the assistant's eyes.

Inside an immersive WebXR session the page cannot open a camera (WebXR owns
it), so the frame has to come from somewhere else. The daemon can pull a still
from any HTTP camera the PC can reach - a phone running an IP-webcam app, a
security camera, a Raspberry Pi cam - and hand it to the vision model.

Supported sources:
  * a plain JPEG URL            (``http://host:8080/shot.jpg``)
  * an MJPEG stream             (``http://host:8080/video_feed``) - the first
    frame of the multipart stream is extracted
  * ``file://`` paths are rejected; use ``JARVIS_VISION_URL`` with http(s)
"""
from __future__ import annotations

import os
import urllib.error
import urllib.request
from typing import Optional

VISION_URL_ENV = "JARVIS_VISION_URL"
DEFAULT_TIMEOUT = 12.0

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def configured_url() -> Optional[str]:
    """The camera URL this machine should use as the assistant's eyes."""
    url = os.environ.get(VISION_URL_ENV, "").strip()
    return url or None


def _find_jpeg_start(data: bytes) -> int:
    marker = b"\xff\xd8\xff"
    index = data.find(marker)
    return index if index >= 0 else -1


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def detect_mime(payload: bytes) -> str:
    """Guess the image type of a downloaded payload."""
    if payload[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if payload[:8] == PNG_MAGIC:
        return "image/png"
    if payload[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if payload[:2] == b"BM":
        return "image/bmp"
    return "image/jpeg"


def extract_jpeg(payload: bytes) -> Optional[bytes]:
    """Pull an image out of a raw response or an MJPEG multipart stream."""
    if not payload:
        return None
    if payload[:3] == b"\xff\xd8\xff":
        return payload
    if payload[:8] == PNG_MAGIC:
        return payload

    start = _find_jpeg_start(payload)
    if start >= 0:
        end = payload.rfind(b"\xff\xd9")
        if end < 0:
            end = len(payload) - 1
        return payload[start:end + 2]

    # A multipart stream that carries PNG parts instead of JPEG.
    png_start = payload.find(PNG_MAGIC)
    if png_start >= 0:
        png_end = payload.find(b"IEND\\xaeB`\\x82", png_start)
        if png_end > 0:
            return payload[png_start:png_end + 8]
        return payload[png_start:]

    return None


def fetch_frame(url: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT) -> bytes:
    """Download one camera frame. Raises RuntimeError with a readable reason."""
    target = (url or configured_url() or "").strip()
    if not target:
        raise RuntimeError(
            "no camera source configured - set {0} to a JPEG or MJPEG URL".format(VISION_URL_ENV)
        )
    if not target.lower().startswith(("http://", "https://")):
        raise RuntimeError("the camera source must be an http(s) URL")

    request = urllib.request.Request(target, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read(4 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("camera HTTP {0}".format(exc.code)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("camera unreachable: {0}".format(exc.reason)) from exc
    except Exception as exc:
        raise RuntimeError("camera failed: {0}".format(exc)) from exc

    frame = extract_jpeg(payload)
    if not frame:
        raise RuntimeError("the camera did not return an image frame")
    return frame
