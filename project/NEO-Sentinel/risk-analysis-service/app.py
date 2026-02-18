from flask import Flask, jsonify, render_template_string
import requests
import logging
import os

# app.py - risk-analysis-service

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Internal Service URLs
ASTEROID_SERVICE_URL = os.environ.get("ASTEROID_SERVICE_URL", "http://asteroid-service:5001")
USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://user-service:5002")

def get_internal_data(url):
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        logger.error(f"Service communication error: {str(e)}")
        return None, str(e)

@app.route("/report/<user_id>", methods=["GET"])
def generate_risk_report(user_id):
    # 1. Fetch User Data
    user_data, error = get_internal_data(f"{USER_SERVICE_URL}/users/{user_id}")
    if error:
        return jsonify({"error": f"User service unreachable: {error}"}), 503
    if not user_data:
        return jsonify({"error": "User not found"}), 404

    threshold = user_data.get("risk_threshold_km", 1000000.0)

    # 2. Fetch Asteroid Data
    asteroid_data, error = get_internal_data(f"{ASTEROID_SERVICE_URL}/asteroids")
    if error:
        return jsonify({"error": f"Asteroid service unreachable: {error}"}), 503

    # 3. Logic: Filter asteroids within the user's risk threshold
    # Note: NASA miss distances are large. If miss_distance_km < threshold, it's a 'hit'
    risky_objects = [
        {
            "id": a["id"],
            "name": a["name"],
            "diameter_km": round(a["diameter_km"], 4),
            "miss_distance_km": round(a["miss_distance_km"], 2),
            "is_hazardous": a["is_hazardous"]
        }
        for a in asteroid_data
        if a.get("miss_distance_km") is not None and a["miss_distance_km"] <= threshold
    ]

    return jsonify({
        "user": user_data["name"],
        "alert_threshold_km": threshold,
        "risky_objects_found": len(risky_objects),
        "objects": risky_objects,
        "summary": f"Analyzed {len(asteroid_data)} objects. Found {len(risky_objects)} within {threshold:,} km."
    }), 200

@app.route("/dashboard/<user_id>")
def dashboard(user_id):
    # Internal call to the report route logic
    report_response, status = generate_risk_report(user_id)
    
    if status != 200:
        return f"<h1>Error</h1><p>{report_response.get_json().get('error')}</p>", status

    report = report_response.get_json()

    html = """
    <html>
        <head><title>NEO-Sentinel Dashboard</title></head>
        <body style="font-family: sans-serif; padding: 20px;">
            <h1>NEO-Sentinel Risk Report for {{ report.user }}</h1>
            <p><strong>Alert Threshold:</strong> {{ "{:,}".format(report.alert_threshold_km) }} km</p>
            <div style="background: #f4f4f4; padding: 15px; border-radius: 5px;">
                <h3>Summary: {{ report.summary }}</h3>
            </div>
            <hr>
            <ul>
                {% for obj in report.objects %}
                <li>
                    <strong>{{ obj.name }}</strong><br>
                    Distance: {{ "{:,}".format(obj.miss_distance_km) }} km | 
                    Diameter: {{ obj.diameter_km }} km 
                    {% if obj.is_hazardous %}<span style="color: red;">[POTENTIALLY HAZARDOUS]</span>{% endif %}
                </li>
                {% endfor %}
            </ul>
            {% if not report.objects %}
                <p>No immediate threats found within your threshold.</p>
            {% endif %}
        </body>
    </html>
    """
    return render_template_string(html, report=report)

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "service": "risk-analysis-service"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003)