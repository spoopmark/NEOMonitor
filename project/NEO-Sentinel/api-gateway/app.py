from flask import Flask, request, jsonify
import requests
from functools import wraps
import logging
import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from proxy import ProxyClient

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiting setup with Redis storage
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri=REDIS_URL,
    default_limits=["200 per day", "50 per hour"],
    storage_options={"connection_pool_kwargs": {"max_connections": 50}},
    swallow_errors=True,  # Continue if Redis is down
)
logger.info(f"Rate limiter initialized with Redis: {REDIS_URL}")

ASTEROID_SERVICE = os.environ.get(
    "ASTEROID_SERVICE_URL", "http://asteroid-service:5001"
)
USER_SERVICE = os.environ.get("USER_SERVICE_URL", "http://user-service:5002")
RISK_SERVICE = os.environ.get("RISK_SERVICE_URL", "http://risk-service:5003")

SERVICE_URLS = {
    "asteroid": ASTEROID_SERVICE,
    "user": USER_SERVICE,
    "risk": RISK_SERVICE,
}

# Proxy client for connection reuse and centralized error handling
proxy_client = ProxyClient(timeout=int(os.environ.get("PROXY_TIMEOUT", "10")))


def log_request(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        logger.info(f"[{request.method}] {request.path} - {request.remote_addr}")
        return f(*args, **kwargs)

    return decorated_function


def proxy_request(service_url, path, method="GET", params=None):
    """Generic proxy function to forward requests to downstream services."""
    try:
        url = f"{service_url}{path}"
        if method == "GET":
            response = requests.get(url, params=params, timeout=10)
        elif method == "POST":
            response = requests.post(url, json=request.get_json(), timeout=10)
        else:
            return jsonify({"error": "Method not supported"}), 405

        return response.json(), response.status_code
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error to {service_url}")
        return jsonify({"error": f"Service unavailable: {service_url}"}), 503
    except requests.exceptions.Timeout:
        logger.error(f"Timeout connecting to {service_url}")
        return jsonify({"error": "Service timeout"}), 504
    except Exception as e:
        logger.error(f"Proxy error: {str(e)}")
        return jsonify({"error": "Internal gateway error"}), 500


@app.route("/asteroids", methods=["GET"])
@limiter.limit("30 per hour")  # Strict limit to protect NASA API
@log_request
def get_asteroids():
    """Proxy to asteroid service. Limited to 30 requests/hour to protect NASA API."""
    params = request.args.to_dict()
    data, status = proxy_client.request(
        ASTEROID_SERVICE, "/asteroids", method="GET", params=params
    )
    return data, status


@app.route("/users/<user_id>", methods=["GET"])
@limiter.limit("100 per hour")
@log_request
def get_user(user_id):
    """Proxy to user service."""
    data, status = proxy_client.request(USER_SERVICE, f"/users/{user_id}")
    return data, status


@app.route("/users/<user_id>/watchlist", methods=["GET"])
@limiter.limit("100 per hour")
@log_request
def get_watchlist(user_id):
    """Proxy to user service watchlist endpoint."""
    params = request.args.to_dict()
    data, status = proxy_client.request(
        USER_SERVICE, f"/users/{user_id}/watchlist", params=params
    )
    return data, status


@app.route("/report/<user_id>", methods=["GET"])
@limiter.limit("40 per hour")  # More generous than asteroids, but still protected
@log_request
def get_report(user_id):
    """Proxy to risk analysis service. Generates report by orchestrating services."""
    data, status = proxy_client.request(RISK_SERVICE, f"/report/{user_id}")
    return data, status


@app.route("/dashboard/<user_id>", methods=["GET"])
@limiter.limit("40 per hour")
@log_request
def get_dashboard(user_id):
    """Proxy dashboard to risk service. HTML rendering is expensive."""
    try:
        response = proxy_client.session.get(
            f"{RISK_SERVICE}/dashboard/{user_id}", timeout=proxy_client.timeout
        )
        return response.text, response.status_code, {"Content-Type": "text/html"}
    except Exception as e:
        logger.error(f"Dashboard proxy error: {str(e)}")
        return jsonify({"error": "Dashboard service unavailable"}), 503


@app.route("/health", methods=["GET"])
@log_request
def health_check():
    """Check health of all downstream services. NOT rate-limited."""
    health_status = {"gateway": "healthy", "services": {}}

    for service_name, service_url in SERVICE_URLS.items():
        try:
            response = proxy_client.session.get(f"{service_url}/health", timeout=5)
            if response.status_code == 200:
                health_status["services"][service_name] = "healthy"
            else:
                health_status["services"][service_name] = "unhealthy"
        except Exception as e:
            logger.warning(f"Health check failed for {service_name}: {str(e)}")
            health_status["services"][service_name] = "unreachable"

    # Overall status is degraded if any service is down
    if any(s != "healthy" for s in health_status["services"].values()):
        health_status["gateway"] = "degraded"

    return jsonify(health_status), 200


@app.route("/", methods=["GET"])
@log_request
def index():
    """API Gateway root endpoint with service map."""
    return (
        jsonify(
            {
                "service": "NEO-Sentinel API Gateway",
                "version": "1.0.0",
                "routes": {
                    "GET /asteroids": "Fetch normalized asteroid data",
                    "GET /users/<user_id>": "Get user profile",
                    "GET /users/<user_id>/watchlist": "Get user's watchlist (supports sort_by, order, id params)",
                    "GET /report/<user_id>": "Generate risk report",
                    "GET /dashboard/<user_id>": "View HTML dashboard",
                    "GET /health": "Check service health",
                    "GET /": "This message",
                },
                "openapi_docs": "/openapi.yaml (see project repo)",
            }
        ),
        200,
    )


@app.errorhandler(404)
def not_found(e):
    logger.warning(f"404 Not Found: {request.path}")
    return jsonify({"error": "Endpoint not found", "path": request.path}), 404


@app.errorhandler(500)
def internal_error(e):
    logger.error(f"500 Internal Server Error: {str(e)}")
    return jsonify({"error": "Internal gateway error"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
