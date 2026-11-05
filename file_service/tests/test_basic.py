import io
from app import app

client = app.test_client()

def test_health():
    assert client.get("/health").status_code == 200

def test_rejects_bad_extension():
    data = {"file": (io.BytesIO(b"x"), "evil.exe")}
    r = client.post("/upload", data=data, content_type="multipart/form-data")
    assert r.status_code == 400

def test_accepts_video():
    data = {"file": (io.BytesIO(b"fake video bytes"), "clip.mp4")}
    r = client.post("/upload", data=data, content_type="multipart/form-data")
    assert r.status_code == 201