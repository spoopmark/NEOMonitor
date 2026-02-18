from flask import Flask, request, jsonify
import requests
import logging
import os
import json
import redis
from datetime import datetime, timezone
from functools import wraps

# app.py - asteroid-service

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
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

CACHE_TTL_SECONDS = 3600  # 1 hour
http_session = requests.Session()

def get_nasa_api_key():
    secret_file = "/run/secrets/nasa_api_key"
    if os.path.isfile(secret_file):
        try:
            with open(secret_file, "r") as f:
                api_key = f.read().strip()
                if api_key: return api_key
        except Exception as e:
            logger.warning(f"Failed to read Docker secret: {str(e)}")
    return os.environ.get("NASA_API_KEY", "DEMO_KEY") # Fallback to DEMO_KEY

def fetch_neo_feed(date=None):
    api_key = get_nasa_api_key()
    cache_key = f"neo_feed:{date or 'default'}"

    if cache:
        try:
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.info(f"Cache HIT for {cache_key}")
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Cache read error: {str(e)}")

    params = {"api_key": api_key}
    if date:
        params.update({"start_date": date, "end_date": date})

    try:
        logger.info(f"Fetching NASA API (date={date}) - CACHE MISS")
        resp = http_session.get(
            "https://api.nasa.gov/neo/rest/v1/feed", params=params, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

        if cache:
            try:
                cache.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(data))
            except Exception as e:
                logger.warning(f"Cache write error: {str(e)}")
        return data
    except Exception as e:
        logger.error(f"NASA API request failed: {str(e)}")
        return None

def normalize_asteroid_data(raw_data):
    normalized_list = []
    if not raw_data or "near_earth_objects" not in raw_data:
        return normalized_list

    for date_key, asteroids in raw_data.get("near_earth_objects", {}).items():
        for asteroid in asteroids:
            try:
                cad = asteroid.get("close_approach_data", [])
                miss_km = None
                approach_date = None
                
                if cad:
                    # Correcting dictionary traversal for NASA's nested structure
                    miss_km = float(cad[0].get("miss_distance", {}).get("kilometers", 0))
                    approach_date = cad[0].get("close_approach_date")

                diam = asteroid.get("estimated_diameter", {}).get("kilometers", {})
                diameter_km = diam.get("estimated_diameter_max")

                normalized_list.append({
                    "id": asteroid.get("id"),
                    "name": asteroid.get("name"),
                    "diameter_km": diameter_km,
                    "miss_distance_km": miss_km,
                    "is_hazardous": asteroid.get("is_potentially_hazardous_asteroid", False),
                    "close_approach_date": approach_date,
                })
            except (ValueError, TypeError, IndexError):
                continue
    return normalized_list

@app.route("/asteroids", methods=["GET"])
def get_asteroids():
    date = request.args.get("date")
    if date:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    raw_json = fetch_neo_feed(date=date)
    if not raw_json:
        return jsonify({"error": "External data source unavailable"}), 502

    return jsonify(normalize_asteroid_data(raw_json)), 200

@app.route("/health", methods=["GET"])
def health_check():
    api_key = get_nasa_api_key()
    return jsonify({
        "status": "healthy" if api_key else "degraded",
        "service": "asteroid-data-service",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "api_key_configured": bool(api_key),
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)