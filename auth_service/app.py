import os
import logging
import datetime
import jwt
import mysql.connector
from flask import Flask, request, jsonify
from werkzeug.security import check_password_hash

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

JWT_SECRET = os.environ["JWT_SECRET"] 


def get_db():
    return mysql.connector.connect(
        host=os.environ["DB_HOST"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
    )


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if not username or not password:
        return jsonify({"error": "Missing credentials"}), 400

    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, password_hash FROM users WHERE username = %s",
                    (username,))  
        user = cur.fetchone()
    finally:
        conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        app.logger.warning("Failed login for user %s", username)
        return jsonify({"error": "Invalid credentials"}), 401

    token = jwt.encode(
        {"sub": username, "uid": user["id"],
         "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)},
        JWT_SECRET, algorithm="HS256")
    app.logger.info("Login ok for user %s", username)
    return jsonify({"token": token}), 200


@app.route("/validate", methods=["GET", "POST"])
def validate():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return jsonify({"error": "Missing token"}), 401
    try:
        claims = jwt.decode(header[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return jsonify({"error": "Invalid or expired token"}), 401
    return jsonify({"valid": True, "user": claims["sub"]}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)