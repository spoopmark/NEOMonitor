import os
import requests
import logging
from flask import Flask, jsonify, render_template_string

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Service Discovery
ASTEROID_SERVICE = os.environ.get('ASTEROID_SERVICE_URL', 'http://asteroid-service:5001')
USER_SERVICE = os.environ.get('USER_SERVICE_URL', 'http://user-service:5002')

# HTML Template (Embedded for simplicity)
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>NEOMonitor Dashboard</title>
    <style>
        body { font-family: sans-serif; padding: 20px; background: #f0f2f5; }
        .card { background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .danger { color: #d32f2f; font-weight: bold; }
        .safe { color: #388e3c; }
        h1 { color: #1a237e; }
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 12px; border-bottom: 1px solid #ddd; }
        th { background-color: #f8f9fa; }
    </style>
</head>
<body>
    <h1>🛰️ NEOMonitor Risk Analysis</h1>
    
    <div class="card">
        <h2>User Profile: {{ user.name }}</h2>
        <p><strong>Alert Threshold:</strong> {{ "{:,.0f}".format(user.risk_threshold_km) }} km</p>
        <p><strong>Status:</strong> 
            {% if risk_stats.dangerous_count > 0 %}
                <span class="danger">⚠️ {{ risk_stats.dangerous_count }} Threats Detected</span>
            {% else %}
                <span class="safe">✅ No Immediate Threats</span>
            {% endif %}
        </p>
    </div>

    <div class="card">
        <h3>Asteroid Approaches (Today)</h3>
        <table>
            <tr>
                <th>Asteroid Name</th>
                <th>Diameter (Est)</th>
                <th>Miss Distance</th>
                <th>Risk Status</th>
            </tr>
            {% for ast in asteroids %}
            <tr>
                <td>{{ ast.name }}</td>
                <td>{{ "{:.2f}".format(ast.diameter_meters) }} m</td>
                <td>{{ "{:,.0f}".format(ast.miss_distance_km) }} km</td>
                <td>
                    {% if ast.is_risky %}
                        <span class="danger">TOO CLOSE</span>
                    {% else %}
                        <span class="safe">Safe</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>
</body>
</html>
"""

@app.route('/<int:user_id>')
def get_dashboard(user_id):
    try:
        # 1. Get User Config
        user_resp = requests.get(f"{USER_SERVICE}/users/{user_id}")
        if user_resp.status_code != 200:
            return f"User {user_id} not found", 404
        user_data = user_resp.json()
        threshold = user_data['risk_threshold_km']

        # 2. Get Asteroid Data
        neo_resp = requests.get(f"{ASTEROID_SERVICE}/feed")
        if neo_resp.status_code != 200:
            return "Failed to fetch NASA data", 500
        neo_data = neo_resp.json()

        # 3. Analyze Risks
        processed_asteroids = []
        dangerous_count = 0
        
        # Parse nested NASA JSON structure
        count = neo_data.get('element_count', 0)
        near_earth_objects = neo_data.get('near_earth_objects', {})
        
        for date, objects in near_earth_objects.items():
            for obj in objects:
                # Extract key metrics
                name = obj['name']
                diameter = obj['estimated_diameter']['meters']['estimated_diameter_max']
                
                # Get closest approach data
                close_approach = obj['close_approach_data'][0]
                miss_km = float(close_approach['miss_distance']['kilometers'])
                
                is_risky = miss_km < threshold
                if is_risky:
                    dangerous_count += 1

                processed_asteroids.append({
                    "name": name,
                    "diameter_meters": diameter,
                    "miss_distance_km": miss_km,
                    "is_risky": is_risky
                })

        # 4. Render Dashboard
        return render_template_string(
            DASHBOARD_TEMPLATE,
            user=user_data,
            asteroids=processed_asteroids,
            risk_stats={"dangerous_count": dangerous_count}
        )

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return f"Internal System Error: {e}", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003)