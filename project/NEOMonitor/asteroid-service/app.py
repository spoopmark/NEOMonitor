import os
import requests
import redis
import json
import logging
from flask import Flask, jsonify, request
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
NASA_API_KEY = os.environ.get('NASA_API_KEY', 'DEMO_KEY')
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/1')

# Redis Connection
try:
    cache = redis.from_url(REDIS_URL)
    logger.info("Connected to Redis cache")
except Exception as e:
    logger.error(f"Failed to connect to Redis: {e}")
    cache = None

@app.route('/feed', methods=['GET'])
def get_feed():
    # Default to today if no date provided
    today = datetime.now().strftime('%Y-%m-%d')
    start_date = request.args.get('start_date', today)
    
    cache_key = f"nasa_feed_{start_date}"
    
    # 1. Check Cache
    if cache:
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info(f"Cache HIT for {start_date}")
            return jsonify(json.loads(cached_data))

    # 2. Fetch from NASA (Cache Miss)
    logger.info(f"Cache MISS. Fetching from NASA for {start_date}...")
    url = "https://api.nasa.gov/neo/rest/v1/feed"
    params = {
        'start_date': start_date,
        'end_date': start_date,
        'api_key': NASA_API_KEY
    }
    
    try:
        resp = requests.get(url, params=params)
        if resp.status_code != 200:
            return jsonify({"error": "NASA API Error", "details": resp.text}), resp.status_code
        
        data = resp.json()
        
        # 3. Save to Cache (Expires in 1 hour = 3600 seconds)
        if cache:
            cache.setex(cache_key, 3600, json.dumps(data))
            
        return jsonify(data)
        
    except Exception as e:
        logger.error(f"Error fetching NASA data: {e}")
        return jsonify({"error": "Internal Server Error"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)