from app import app

def test_health():
    assert app.test_client().get("/health").status_code == 200

def test_upload_requires_login():
    assert app.test_client().get("/upload").status_code == 302