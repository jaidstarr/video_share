import os
import jwt
from app import app

client = app.test_client()

def test_health():
    assert client.get("/health").status_code == 200

def test_validate_rejects_missing_token():
    assert client.get("/validate").status_code == 401

def test_validate_rejects_garbage_token():
    r = client.get("/validate", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401

def test_validate_accepts_good_token():
    token = jwt.encode({"sub": "tester"}, os.environ["JWT_SECRET"], algorithm="HS256")
    r = client.get("/validate", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

def test_login_rejects_missing_credentials():
    r = client.post("/login", json={})
    assert r.status_code == 400