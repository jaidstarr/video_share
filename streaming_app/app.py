import os
import time
import logging
from functools import wraps
from urllib.parse import quote
from mysql.connector import pooling

import requests
import mysql.connector
from flask import (Flask, request, jsonify, redirect, Response,
                   render_template_string, stream_with_context)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
_pool = None

DB_CONFIG = {
    "host": os.environ["DB_HOST"],
    "user": os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
    "database": os.environ["DB_NAME"],
}
AUTH_URL = os.environ["AUTH_URL"]              # .../validate
AUTH_LOGIN_URL = os.environ["AUTH_LOGIN_URL"]  # .../login
FILE_BASE_URL = os.environ["FILE_BASE_URL"]    # .../files

LOGIN_HTML = """
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>Video Streaming - Login</title></head><body>
<h1>Login for Video Streaming</h1>
{% if error %}<p style="color:red">{{ error }}</p>{% endif %}
<form action="/login" method="POST">
  <p><label>Username:</label><br><input type="text" name="username" required></p>
  <p><label>Password:</label><br><input type="password" name="password" required></p>
  <button type="submit">Log in</button>
</form></body></html>
"""

VIDEOS_HTML = """
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>Available Videos</title></head><body>
<h1>Available Videos</h1><p>Signed in as {{ user }} | <a href="/logout">Log out</a></p><hr>
{% if not videos %}<p>No videos uploaded yet.</p>{% endif %}
{% for v in videos %}
<div style="margin-bottom:40px;">
  <h2>{{ v.title }}</h2>
  <video width="640" controls>
    <source src="/stream/{{ v.filename | urlencode }}" type="video/mp4">
  </video>
</div><hr>
{% endfor %}
</body></html>
"""


def get_db_connection(retries=5, delay=2):
    global _pool
    for attempt in range(retries):
        try:
            if _pool is None:
                _pool = pooling.MySQLConnectionPool(
                    pool_name="streaming", pool_size=5, **DB_CONFIG)
            return _pool.get_connection()
        except mysql.connector.Error as err:
            app.logger.warning("DB connect failed (%d/%d): %s",
                               attempt + 1, retries, err)
            if attempt == retries - 1:
                raise
            time.sleep(delay)


def check_token():
    token = request.cookies.get("token", "")
    if not token:
        return None
    r = requests.get(AUTH_URL, headers={"Authorization": f"Bearer {token}"}, timeout=5)
    return r.json().get("user") if r.status_code == 200 else None


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            user = check_token()
        except requests.RequestException:
            app.logger.error("Auth service unreachable")
            return jsonify({"error": "Authentication service unavailable"}), 503
        if not user:
            return redirect("/")
        return f(user, *args, **kwargs)
    return wrapper


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/")
def home():
    return render_template_string(LOGIN_HTML, error=None)


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not username or not password:
        return render_template_string(LOGIN_HTML, error="Missing credentials"), 400
    try:
        r = requests.post(AUTH_LOGIN_URL,
                          json={"username": username, "password": password}, timeout=5)
    except requests.RequestException:
        app.logger.error("Auth service unreachable during login")
        return jsonify({"error": "Authentication service unavailable"}), 503
    if r.status_code != 200:
        return render_template_string(LOGIN_HTML, error="Invalid username or password"), 401
    resp = redirect("/videos", code=303)
    resp.set_cookie("token", r.json()["token"], httponly=True, samesite="Lax", max_age=3600)
    return resp


@app.route("/logout")
def logout():
    resp = redirect("/")
    resp.delete_cookie("token")
    return resp


@app.route("/videos")
@login_required
def list_videos(user):
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT title, filename FROM videos ORDER BY uploaded_at DESC")
        videos = cur.fetchall()
        cur.close()
        conn.close()
    except mysql.connector.Error as err:
        app.logger.error("DB error listing videos: %s", err)
        return jsonify({"error": "Database unavailable"}), 503
    return render_template_string(VIDEOS_HTML, videos=videos, user=user)


@app.route("/stream/<path:filename>")
@login_required
def stream(user, filename):
    # only serve files that are actually registered in the DB
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM videos WHERE filename = %s", (filename,))
        found = cur.fetchone()
        cur.close()
        conn.close()
    except mysql.connector.Error as err:
        app.logger.error("DB error in stream: %s", err)
        return jsonify({"error": "Database unavailable"}), 503
    if not found:
        return jsonify({"error": "Not found"}), 404

    headers = {}
    if "Range" in request.headers:           # lets the player seek
        headers["Range"] = request.headers["Range"]
    try:
        upstream = requests.get(f"{FILE_BASE_URL}/{quote(filename)}",
                                headers=headers, stream=True, timeout=10)
    except requests.RequestException:
        app.logger.error("File service unreachable")
        return jsonify({"error": "File service unavailable"}), 503

    passthrough = {k: v for k, v in upstream.headers.items()
                   if k in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges")}
    return Response(stream_with_context(upstream.iter_content(65536)),
                    status=upstream.status_code, headers=passthrough)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003, debug=True)