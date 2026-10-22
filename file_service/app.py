import os
import uuid
import logging
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "/app/storage/videos")
ALLOWED_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv"}
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part in request"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    original = secure_filename(file.filename)
    base, ext = os.path.splitext(original)
    if not base or ext.lower() not in ALLOWED_EXTENSIONS:
        app.logger.warning("Rejected upload: bad name or extension")
        return jsonify({"error": "Invalid file type"}), 400

    filename = f"{uuid.uuid4().hex[:8]}_{original}"
    file.save(os.path.join(UPLOAD_FOLDER, filename))
    app.logger.info("Stored file %s", filename)

    return jsonify({"message": "File uploaded successfully",
                    "filename": filename}), 201


@app.route("/files/<path:filename>", methods=["GET"])
def get_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=False)


@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large"}), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)