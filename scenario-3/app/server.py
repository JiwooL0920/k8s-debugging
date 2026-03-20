import os
import time
import threading
from flask import Flask, jsonify, request

app = Flask(__name__)

STARTUP_DELAY = int(os.environ.get("STARTUP_DELAY_SECONDS", "5"))
ready = False

def initialize():
    global ready
    time.sleep(STARTUP_DELAY)
    ready = True

threading.Thread(target=initialize, daemon=True).start()

AVAILABLE_MODELS = [
    {"id": "default", "version": "1.0.0"},
    {"id": "experimental", "version": "0.9.0"},
]


@app.route("/health")
def health():
    """Liveness probe - am I alive?"""
    return jsonify({"status": "ok"}), 200


@app.route("/ready")
def ready_check():
    """Readiness probe - am I ready to serve traffic?"""
    if ready:
        return jsonify({"status": "ready"}), 200
    return jsonify({"status": "initializing"}), 503


@app.route("/")
def index():
    return jsonify({
        "service": "inference-api",
        "version": os.environ.get("APP_VERSION", "unknown"),
        "environment": os.environ.get("ENVIRONMENT", "unknown"),
    })


@app.route("/api/v1/models", methods=["GET"])
def list_models():
    return jsonify({"models": AVAILABLE_MODELS}), 200


@app.route("/api/v1/predict", methods=["POST"])
def predict():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return jsonify({"error": "Database not configured"}), 500

    body = request.get_json(silent=True) or {}
    model_id = body.get("model_id", "default")
    data = body.get("data", {})

    return jsonify({
        "status": "success",
        "model_id": model_id,
        "input_keys": list(data.keys()),
        "processed": True,
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
