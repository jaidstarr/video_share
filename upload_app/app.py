import os
import time
import logging
from functools import wraps

import requests
import mysql.connector
from flask import (Flask, request, jsonify, redirect,
                   render_template_string)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB
ALLOWED_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv"}

DB_CONFIG = {
    "host": os.environ["DB_HOST"],
    "user": os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
    "database": os.environ["DB_NAME"],
}
AUTH_URL = os.environ["AUTH_URL"]              # .../validate
AUTH_LOGIN_URL = os.environ["AUTH_LOGIN_URL"]  # .../login
FILE_URL = os.environ["FILE_URL"]              # .../upload

LOGIN_HTML = """
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>Video Share - Login</title></head><body>
<h1>Login for Video Upload</h1>
{% if error %}<p style="color:red">{{ error }}</p>{% endif %}
<form action="/login" method="POST">
  <p><label>Username:</label><br><input type="text" name="username" required></p>
  <p><label>Password:</label><br><input type="password" name="password" required></p>
  <button type="submit">Log in</button>
</form></body></html>
"""

HOME_HTML = """
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>Video Share</title></head><body>
<h1>Video Share</h1>
<p>Signed in as {{ user }} | <a href="/logout">Log out</a></p>
<ul>
  <li><a href="{{ upload_url }}">Upload a video</a></li>
</ul>
</body></html>
"""

UPLOAD_HTML = """
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>Upload Video</title></head><body>
<h1>Upload Video</h1>
<p>Signed in as {{ user }} | <a href="/logout">Log out</a></p>
<p><a href="/">Home</a></p>
{% if message %}<p style="color:green">{{ message }}</p>{% endif %}
{% if error %}<p style="color:red">{{ error }}</p>{% endif %}
<form action="/upload" method="POST" enctype="multipart/form-data">
  <p><label>Video Title:</label><br>
     <input type="text" name="title" maxlength="100" required></p>
  <p><label>Select Video File (mp4, webm, mov, mkv):</label><br>
     <input type="file" name="file" accept="video/*" required></p>
  <button type="submit">Upload</button>
</form></body></html>
"""


def get_db_connection(retries=5, delay=2):
    for attempt in range(retries):
        try:
            return mysql.connector.connect(**DB_CONFIG)
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
    r = requests.get(AUTH_URL,
                     headers={"Authorization": f"Bearer {token}"}, timeout=5)
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


def menu_urls():
    host = request.host.split(":")[0]
    return f"http://{host}:5000/upload", f"http://{host}:5003/videos"


@app.route("/")
def home():
    try:
        user = check_token()
    except requests.RequestException:
        user = None
    if not user:
        return render_template_string(LOGIN_HTML, error=None)
    upload_url, view_url = menu_urls()
    return render_template_string(HOME_HTML, user=user, upload_url=upload_url, view_url=view_url)


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not username or not password:
        return render_template_string(LOGIN_HTML, error="Missing credentials"), 400
    try:
        r = requests.post(AUTH_LOGIN_URL,
                          json={"username": username, "password": password},
                          timeout=5)
    except requests.RequestException:
        app.logger.error("Auth service unreachable during login")
        return jsonify({"error": "Authentication service unavailable"}), 503
    if r.status_code != 200:
        return render_template_string(
            LOGIN_HTML, error="Invalid username or password"), 401
    resp = redirect("/", code=303)
    resp.set_cookie("token", r.json()["token"], httponly=True,
                    samesite="Lax", max_age=3600)
    return resp


@app.route("/logout")
def logout():
    resp = redirect("/")
    resp.delete_cookie("token")
    return resp


@app.route("/upload", methods=["GET"])
@login_required
def upload_form(user):
    return render_template_string(UPLOAD_HTML, user=user,
                                  message=None, error=None)


@app.route("/upload", methods=["POST"])
@login_required
def upload_video(user):
    title = request.form.get("title", "").strip()
    file = request.files.get("file")

    def fail(msg, code):
        return render_template_string(UPLOAD_HTML, user=user,
                                      message=None, error=msg), code

    if not title or len(title) > 100:
        return fail("Title is required (max 100 characters)", 400)
    if file is None or file.filename == "":
        return fail("A video file is required", 400)
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        app.logger.warning("User %s tried to upload disallowed type %s", user, ext)
        return fail("Unsupported file type", 400)

    # send the file to the file service
    try:
        file_response = requests.post(
            FILE_URL,
            files={"file": (file.filename, file.stream, file.mimetype)},
            timeout=120)
    except requests.RequestException:
        app.logger.error("File service unreachable")
        return fail("File service unavailable, try again later", 503)
    if file_response.status_code != 201:
        app.logger.error("File service returned %s", file_response.status_code)
        return fail("Failed to store video file", 500)

    file_data = file_response.json()
    filename = file_data["filename"]
    filepath = file_data.get("filepath", filename)

    # save the metadata
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO videos (title, filename, filepath) VALUES (%s, %s, %s)",
            (title, filename, filepath))
        conn.commit()
        cur.close()
        conn.close()
    except mysql.connector.Error as err:
        app.logger.error("DB error saving metadata for %s: %s", filename, err)
        return fail("Database unavailable, try again later", 503)

    app.logger.info("User %s uploaded %s", user, filename)
    return render_template_string(UPLOAD_HTML, user=user,
                                  message=f"Uploaded '{title}' successfully",
                                  error=None), 201


@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large (max 500 MB)"}), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)