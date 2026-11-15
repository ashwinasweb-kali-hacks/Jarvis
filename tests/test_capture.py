"""Tests for the server-side camera capture."""
import pytest

from jarvis import capture


def test_detect_mime():
    assert capture.detect_mime(b"\xff\xd8\xffabc") == "image/jpeg"
    assert capture.detect_mime(b"\x89PNG\r\n\x1a\nabc") == "image/png"
    assert capture.detect_mime(b"GIF89a...") == "image/gif"


def test_extract_jpeg_from_multipart_stream():
    jpeg = b"\xff\xd8\xff" + b"payload" + b"\xff\xd9"
    stream = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n--frame--"
    assert capture.extract_jpeg(stream) == jpeg


def test_extract_png_from_multipart_stream():
    png = b"\x89PNG\r\n\x1a\n" + b"data" + b"IEND\xaeB`\x82"
    stream = b"--frame\r\nContent-Type: image/png\r\n\r\n" + png + b"\r\n"
    extracted = capture.extract_jpeg(stream)
    assert extracted.startswith(b"\x89PNG\r\n\x1a\n")
    assert b"IEND" in extracted


def test_fetch_frame_requires_a_url():
    with pytest.raises(RuntimeError) as exc:
        capture.fetch_frame("")
    assert "JARVIS_VISION_URL" in str(exc.value)


def test_fetch_frame_rejects_non_http():
    with pytest.raises(RuntimeError) as exc:
        capture.fetch_frame("file:///C:/secret.jpg")
    assert "http" in str(exc.value)


def test_configured_url_reads_the_environment(monkeypatch):
    monkeypatch.delenv(capture.VISION_URL_ENV, raising=False)
    assert capture.configured_url() is None
    monkeypatch.setenv(capture.VISION_URL_ENV, "http://10.0.0.5:8080/shot.jpg")
    assert capture.configured_url() == "http://10.0.0.5:8080/shot.jpg"


def test_fetch_frame_from_a_local_camera(monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    frame = b"\xff\xd8\xff" + b"pixels" + b"\xff\xd9"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(frame)))
            self.end_headers()
            self.wfile.write(frame)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        data = capture.fetch_frame("http://127.0.0.1:{0}/shot.jpg".format(port))
        assert data == frame
    finally:
        server.shutdown()
