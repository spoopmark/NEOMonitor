import os
import requests
import logging
from flask import Flask, request, jsonify, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Load Configuration
ASTEROID_SERVICE_URL = os.environ.get('ASTEROID_SERVICE_URL', 'http://asteroid-service:5001')
USER_SERVICE_URL = os.environ.get('USER_SERVICE_URL', 'http://user-service:5002')
RISK_SERVICE_URL = os.environ.get('RISK_SERVICE_URL', 'http://risk-service:5003')
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/0')

# Setup Rate Limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri=REDIS_URL,
    default_limits=["50 per hour"]
)

def proxy_request(service_url, endpoint):
    """Forward request to the downstream microservice."""
    try:
        resp = requests.request(
            method=request.method,
            url=f"{service_url}/{endpoint}",
            headers={key: value for (key, value) in request.headers if key != 'Host'},
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            params=request.args
        )
        # Return the response from the microservice exactly as received
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for (name, value) in resp.raw.headers.items()
                   if name.lower() not in excluded_headers]
        
        return Response(resp.content, resp.status_code, headers)
    except requests.exceptions.RequestException as e:
        logger.error(f"Service connection failed: {str(e)}")
        return jsonify({"error": "Service unavailable"}), 503

# --- Routes ---

@app.route('/')
def index():
    return jsonify({
        "name": "NEOMonitor API Gateway",
        "status": "operational",
        "endpoints": {
            "asteroids": "/neo/feed",
            "dashboard": "/dashboard/<user_id>",
            "user": "/user/<user_id>"
        }
    })

@app.route('/neo/<path:path>', methods=['GET', 'POST'])
def asteroid_proxy(path):
    return proxy_request(ASTEROID_SERVICE_URL, path)

@app.route('/user/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def user_proxy(path):
    return proxy_request(USER_SERVICE_URL, path)

@app.route('/dashboard/<path:path>', methods=['GET'])
def risk_proxy(path):
    return proxy_request(RISK_SERVICE_URL, path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)