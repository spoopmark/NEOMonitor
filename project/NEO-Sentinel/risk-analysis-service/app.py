from flask import Flask, jsonify, render_template_string
import requests

app = Flask(__name__)

# URLs of our other services
ASTEROID_SERVICE_URL = "http://asteroid-service:5001"
USER_SERVICE_URL = "http://user-service:5002"

@app.route('/report/<user_id>', methods=['GET'])
def generate_risk_report(user_id):
    # get user data 
    user_response = requests.get(f"{USER_SERVICE_URL}/users/{user_id}")
    if user_response.status_code != 200:
        return jsonify({"error": "Could not find user"}), 404
    
    user_data = user_response.json()
    threshold = user_data['risk_threshold_km']

    # 2. Get Normalized Asteroid Data from Asteroid Service
    asteroid_response = requests.get(f"{ASTEROID_SERVICE_URL}/asteroids")
    if asteroid_response.status_code != 200:
        return jsonify({"error": "Asteroid service is down"}), 500
    
    all_asteroids = asteroid_response.json()

    # 3. Filter asteroids that exceed the user's size threshold
    risky_asteroids = [
        a for a in all_asteroids 
        if a.get('miss_distance_km') is not None and a['miss_distance_km'] <= threshold
    ]

    # 4. Return the final Recommendation JSON
    return jsonify({
        "user": user_data['name'],
        "alert_threshold": threshold,
        "risky_objects_found": len(risky_asteroids),
        "objects": risky_asteroids,
        "summary": f"Found {len(risky_asteroids)} asteroids within {threshold}km of Earth."
    })
    
from flask import render_template_string

@app.route('/dashboard/<user_id>')
def dashboard(user_id):
    # Call your own report logic
    report = generate_risk_report(user_id).get_json()
    
    html = """
    <h1>NEO-Sentinel Risk Report for {{ report.user }}</h1>
    <p>Threshold: {{ report.alert_threshold }} km</p>
    <ul>
        {% for obj in report.objects %}
        <li><strong>{{ obj.name }}</strong> - {{ obj.diameter_km|round(3) }} km wide</li>
        {% endfor %}
    </ul>
    """
    return render_template_string(html, report=report)
    
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "risk-analysis-service"}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003) # Risk Service lives on 5003