import os
import time
from flask import Flask, jsonify, request

import threading

app = Flask(__name__)

STARTUP_DELAY = int(os.environ.get("STARTUP_DELAY_SECONDS", "5"))
ready = False

def initialize():
    global ready
    time.sleep(STARTUP_DELAY)
    ready = True

threading.Thread(target=initialize, daemon=True).start()

@app.route("/healthz")
def healthz():
    """Liveness probe - am I alive?"""
    return jsonify({"status": "ok"}), 200

@app.route("/readyz")
def readyz():
    """Readiness probe - am I ready to serve traffic?"""
    if ready:
        return jsonify({"status": "ready"}), 200
    return jsonify({"status": "initializing"}), 503

@app.route("/")
def index():
    return jsonify({
        "service": "data-processor",
        "version": os.environ.get("APP_VERSION", "unknown"),
        "environment": os.environ.get("ENVIRONMENT", "unknown"),
    })

@app.route("/api/v1/data", methods=["POST"])
def process_data():
    data = request.get_json(silent=True) or {}
    records = data.get("records", [])
    return jsonify({"processed": True, "count": len(records)}), 202

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
