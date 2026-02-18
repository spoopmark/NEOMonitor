from flask import Flask, request, jsonify
import requests
from functools imfrom flask import Flask, request, jsonify
import requests
from functools import wraps
import logging
import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# app.py - api-gateway

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Rate limiting setup - Fallback to in-memory if Redis is down
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri=REDIS_URL,
    default_limits=["200 per day", "50 per hour"],
    swallow_errors=True,
)

# Service Configuration
ASTEROID_SERVICE = os.environ.get("ASTEROID_SERVICE_URL", "http://asteroid-service:5001")
USER_SERVICE = os.environ.get("USER_SERVICE_URL", "http://user-service:5002")
RISK_SERVICE = os.environ.get("RISK_SERVICE_URL", "http://risk-service:5003")

SERVICE_URLS = {
    "asteroid": ASTEROID_SERVICE,
    "user": USER_SERVICE,
    "risk": RISK_SERVICE,
}

# Persistent session for connection pooling
http_session = requests.Session()
TIMEOUT = int(os.environ.get("PROXY_TIMEOUT", "10"))

def log_request(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        logger.info(f"[{request.method}] {request.path} - {request.remote_addr}")
        return f(*args, **kwargs)
    return decorated_function

def proxy_request(base_url, path, method="GET", **kwargs):
    """Helper to forward requests to internal services."""
    url = f"{base_url}{path}"
    try:
        resp = http_session.request(method, url, timeout=TIMEOUT, **kwargs)
        # Attempt to return JSON, fallback to text if not JSON (e.g. for HTML dashboards)
        try:
            return resp.json(), resp.status_code
        except ValueError:
            return resp.text, resp.status_code
    except requests.exceptions.RequestException as e:
        logger.error(f"Proxy error for {url}: {str(e)}")
        return {"error": "Service unavailable", "details": str(e)}, 503

# --- Routes ---

@app.route("/asteroids", methods=["GET"])
@limiter.limit("30 per hour")
@log_request
def get_asteroids():
    data, status = proxy_request(ASTEROID_SERVICE, "/asteroids", params=request.args.to_dict())
    return jsonify(data), status

@app.route("/users/<user_id>", methods=["GET"])
@limiter.limit("100 per hour")
@log_request
def get_user(user_id):
    data, status = proxy_request(USER_SERVICE, f"/users/{user_id}")
    return jsonify(data), status

@app.route("/users/<user_id>/watchlist", methods=["GET", "POST"])
@limiter.limit("100 per hour")
@log_request
def handle_watchlist(user_id):
    if request.method == "POST":
        data, status = proxy_request(USER_SERVICE, f"/users/{user_id}/watchlist", method="POST", json=request.get_json())
    else:
        data, status = proxy_request(USER_SERVICE, f"/users/{user_id}/watchlist", params=request.args.to_dict())
    return jsonify(data), status

@app.route("/report/<user_id>", methods=["GET"])
@limiter.limit("40 per hour")
@log_request
def get_report(user_id):
    data, status = proxy_request(RISK_SERVICE, f"/report/{user_id}")
    return jsonify(data), status

@app.route("/dashboard/<user_id>", methods=["GET"])
@limiter.limit("40 per hour")
@log_request
def get_dashboard(user_id):
    """Specialized route for HTML content."""
    content, status = proxy_request(RISK_SERVICE, f"/dashboard/{user_id}")
    if status == 200:
        return content, status, {"Content-Type": "text/html"}
    return jsonify(content), status

@app.route("/health", methods=["GET"])
def health_check():
    health_status = {"gateway": "healthy", "services": {}}
    for name, url in SERVICE_URLS.items():
        try:
            r = http_session.get(f"{url}/health", timeout=2)
            health_status["services"][name] = "healthy" if r.status_code == 200 else "unhealthy"
        except:
            health_status["services"][name] = "unreachable"

    if any(v != "healthy" for v in health_status["services"].values()):
        health_status["gateway"] = "degraded"
    return jsonify(health_status), 200 if health_status["gateway"] == "healthy" else 200

# --- Error Handlers ---

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "Rate limit exceeded", "message": str(e.description)}), 429

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)port wraps
import logging
import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from proxy import ProxyClient

# app.py api-gateway

app = Flask(__name__)

# Standardizing logging format for better traceability
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Rate limiting setup with Redis storage
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri=REDIS_URL,
    default_limits=["200 per day", "50 per hour"],
    storage_options={"connection_pool_kwargs": {"max_connections": 50}},
    swallow_errors=True,
)

# Service Configuration
ASTEROID_SERVICE = os.environ.get("ASTEROID_SERVICE_URL", "http://asteroid-service:5001")
USER_SERVICE = os.environ.get("USER_SERVICE_URL", "http://user-service:5002")
RISK_SERVICE = os.environ.get("RISK_SERVICE_URL", "http://risk-service:5003")

SERVICE_URLS = {
    "asteroid": ASTEROID_SERVICE,
    "user": USER_SERVICE,
    "risk": RISK_SERVICE,
}

# Unified Proxy client for connection reuse (TCP pooling)
# This prevents "Connection Leak" by reusing the same session
proxy_client = ProxyClient(timeout=int(os.environ.get("PROXY_TIMEOUT", "10")))

def log_request(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        logger.info(f"[{request.method}] {request.path} - {request.remote_addr}")
        return f(*args, **kwargs)
    return decorated_function

# --- Routes ---

@app.route("/asteroids", methods=["GET"])
@limiter.limit("30 per hour")
@log_request
def get_asteroids():
    params = request.args.to_dict()
    data, status = proxy_client.request(
        ASTEROID_SERVICE, "/asteroids", method="GET", params=params
    )
    return jsonify(data), status

@app.route("/users/<user_id>", methods=["GET"])
@limiter.limit("100 per hour")
@log_request
def get_user(user_id):
    data, status = proxy_client.request(USER_SERVICE, f"/users/{user_id}")
    return jsonify(data), status

@app.route("/users/<user_id>/watchlist", methods=["GET"])
@limiter.limit("100 per hour")
@log_request
def get_watchlist(user_id):
    params = request.args.to_dict()
    data, status = proxy_client.request(
        USER_SERVICE, f"/users/{user_id}/watchlist", params=params
    )
    return jsonify(data), status

@app.route("/report/<user_id>", methods=["GET"])
@limiter.limit("40 per hour")
@log_request
def get_report(user_id):
    data, status = proxy_client.request(RISK_SERVICE, f"/report/{user_id}")
    return jsonify(data), status

@app.route("/dashboard/<user_id>", methods=["GET"])
@limiter.limit("40 per hour")
@log_request
def get_dashboard(user_id):
    """Proxy dashboard with specialized HTML handling."""
    try:
        # Use the underlying session for direct text/html retrieval
        response = proxy_client.session.get(
            f"{RISK_SERVICE}/dashboard/{user_id}", 
            timeout=proxy_client.timeout
        )
        return response.text, response.status_code, {"Content-Type": "text/html"}
    except requests.exceptions.RequestException as e:
        logger.error(f"Dashboard proxy error: {str(e)}")
        return jsonify({"error": "Dashboard service unavailable"}), 503

@app.route("/health", methods=["GET"])
@log_request
def health_check():
    health_status = {"gateway": "healthy", "services": {}}
    
    for service_name, service_url in SERVICE_URLS.items():
        try:
            # Reusing the proxy_client session for health checks
            response = proxy_client.session.get(f"{service_url}/health", timeout=5)
            health_status["services"][service_name] = "healthy" if response.status_code == 200 else "unhealthy"
        except Exception:
            health_status["services"][service_name] = "unreachable"

    if any(s != "healthy" for s in health_status["services"].values()):
        health_status["gateway"] = "degraded"

    return jsonify(health_status), 200

@app.route("/", methods=["GET"])
@log_request
def index():
    return jsonify({
        "service": "NEO-Sentinel API Gateway",
        "version": "1.0.0",
        "status": "online"
    }), 200

# --- Error Handlers ---

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found", "path": request.path}), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Uncaught Exception: {str(e)}")
    return jsonify({"error": "Internal gateway error"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)