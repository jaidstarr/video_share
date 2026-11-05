from app import app

client = app.test_client()

def test_health():
    assert client.get("/health").status_code == 200

def test_videos_requires_login():
    # no cookie, so the app should redirect to the login page
    assert client.get("/videos").status_code == 302

def test_stream_requires_login():
    assert client.get("/stream/anything.mp4").status_code == 302