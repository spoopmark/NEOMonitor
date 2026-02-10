import os
import requests
from flask import Flask, jsonify, request
import logging
import json
from datetime import datetime
import redis

app = Flask(__name__)

# Configure structured logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Redis cache setup
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/1")
try:
    cache = redis.from_url(REDIS_URL, decode_responses=True)
    cache.ping()
    logger.info("Connected to Redis cache")
except Exception as e:
    logger.warning(f"Redis cache unavailable: {str(e)}. Continuing without cache.")
    cache = None

# Cache configuration
CACHE_TTL_SECONDS = 3600  # 1 hour


class RequestLogger:
    """Middleware to log all requests and responses."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        method = environ.get("REQUEST_METHOD")
        path = environ.get("PATH_INFO")
        remote_addr = environ.get("REMOTE_ADDR")
        logger.info(f"[{method}] {path} from {remote_addr}")
        return self.app(environ, start_response)


app.wsgi_app = RequestLogger(app.wsgi_app)


def get_nasa_api_key():
    """Read NASA API key from Docker secret or environment variable.

    Priority:
    1. Docker Swarm secret: /run/secrets/nasa_api_key
    2. Environment variable: NASA_API_KEY (fallback for local dev)
    """
    # Try Docker secret first (production)
    secret_file = "/run/secrets/nasa_api_key"
    if os.path.isfile(secret_file):
        try:
            with open(secret_file, "r") as f:
                api_key = f.read().strip()
                if api_key:
                    logger.info("Loaded NASA API key from Docker secret")
                    return api_key
        except Exception as e:
            logger.warning(f"Failed to read Docker secret: {str(e)}")

    # Fallback to environment variable (for local development with .env)
    api_key = os.environ.get("NASA_API_KEY")
    if api_key:
        logger.info("Loaded NASA API key from environment variable")
        return api_key

    logger.error(
        "NASA API key not found in Docker secret or NASA_API_KEY environment variable"
    )
    return None


def fetch_neo_feed(date=None):
    """Fetch Near-Earth Objects feed from NASA API with Redis caching."""
    api_key = get_nasa_api_key()
    if not api_key:
        logger.error("NASA API key is not configured")
        return None

    # Generate cache key
    cache_key = f"neo_feed:{date or 'default'}"

    # Try to get from cache
    if cache:
        try:
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.info(f"Cache HIT for {cache_key}")
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Cache read error: {str(e)}")

    # Cache miss or no cache - fetch from NASA API
    params = {"api_key": api_key}
    if date:
        params.update({"start_date": date, "end_date": date})

    try:
        logger.info(f"Fetching NEO feed from NASA API (date={date}) - CACHE MISS")
        resp = requests.get(
            "https://api.nasa.gov/neo/rest/v1/feed", params=params, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(
            f"Successfully fetched NEO data, found {len(data.get('near_earth_objects', {}))} dates"
        )

        # Cache the result
        if cache:
            try:
                cache.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(data))
                logger.info(
                    f"Cached response for {cache_key} TTL: {CACHE_TTL_SECONDS}s"
                )
            except Exception as e:
                logger.warning(f"Cache write error: {str(e)}")

        return data
    except requests.exceptions.Timeout:
        logger.error("NASA API request timeout (10 seconds)")
        return None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error to NASA API: {str(e)}")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error from NASA API: {e.response.status_code} - {str(e)}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request exception: {str(e)}")
        return None
    except json.JSONDecodeError:
        logger.error("Failed to parse NASA API response as JSON")
        return None


def normalize_asteroid_data(raw_data):
    """Normalize raw asteroid data into standard format with error handling."""
    normalized_list = []
    if not raw_data or "near_earth_objects" not in raw_data:
        logger.warning("No near_earth_objects in raw data")
        return normalized_list

    skipped = 0
    for date_key, asteroids in raw_data.get("near_earth_objects", {}).items():
        for asteroid in asteroids:
            try:
                miss_km = None
                cad = asteroid.get("close_approach_data") or []
                if cad:
                    miss = cad[0].get("miss_distance", {}).get("kilometers")
                    miss_km = float(miss) if miss is not None else None

                diameter_km = None
                diam = asteroid.get("estimated_diameter", {}).get("kilometers", {})
                if diam:
                    diameter_km = diam.get("estimated_diameter_max") or diam.get(
                        "estimated_diameter_min"
                    )

                clean_asteroid = {
                    "id": asteroid.get("id"),
                    "name": asteroid.get("name"),
                    "diameter_km": diameter_km,
                    "miss_distance_km": miss_km,
                    "is_hazardous": asteroid.get(
                        "is_potentially_hazardous_asteroid", False
                    ),
                    "close_approach_date": (
                        cad[0].get("close_approach_date") if cad else None
                    ),
                }
                normalized_list.append(clean_asteroid)
            except (KeyError, ValueError, TypeError) as e:
                logger.debug(f"Skipped malformed asteroid entry: {str(e)}")
                skipped += 1
                continue

    logger.info(f"Normalized {len(normalized_list)} asteroids ({skipped} skipped)")
    return normalized_list


@app.route("/asteroids", methods=["GET"])
def get_asteroids():
    """Get normalized asteroid data with optional date filtering."""
    try:
        date = request.args.get("date")  # optional YYYY-MM-DD

        if date:
            # Validate date format
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                logger.warning(f"Invalid date format: {date}")
                return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

        raw_json = fetch_neo_feed(date=date)
        if not raw_json:
            logger.error("Failed to fetch NEO data from NASA API")
            return (
                jsonify({"error": "NASA API unreachable or NASA_API_KEY not set"}),
                502,
            )

        clean_data = normalize_asteroid_data(raw_json)
        logger.info(f"Returning {len(clean_data)} asteroids")
        return jsonify(clean_data), 200
    except Exception as e:
        logger.error(f"Unexpected error in get_asteroids: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    try:
        # Check if NASA API is configured
        api_key = get_nasa_api_key()
        health = {
            "status": "healthy",
            "service": "asteroid-data-service",
            "timestamp": datetime.utcnow().isoformat(),
            "api_key_configured": bool(api_key),
        }

        if not api_key:
            health["status"] = "degraded"
            health["warning"] = "NASA API key not configured"

        return jsonify(health), 200
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return (
            jsonify(
                {
                    "status": "unhealthy",
                    "service": "asteroid-data-service",
                    "error": str(e),
                }
            ),
            503,
        )


@app.errorhandler(404)
def not_found(e):
    logger.warning(f"404 Not Found: {request.path}")
    return jsonify({"error": "Endpoint not found", "path": request.path}), 404


@app.errorhandler(500)
def internal_error(e):
    logger.error(f"500 Internal Server Error: {str(e)}")
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    logger.info("Starting Asteroid Data Service on port 5001")
    app.run(host="0.0.0.0", port=5001)
