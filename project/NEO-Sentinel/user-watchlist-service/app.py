from flask import Flask, jsonify, request

app = Flask(__name__)

# mock database
users = {
    "1": {"id": "1", "name": "Professor", "risk_threshold_km": 0.1},
    "2": {"id": "2", "name": "Student", "risk_threshold_km": 0.5}
}



@app.route('/users/<user_id>', methods=['GET'])
def get_user(user_id):
    user = users.get(user_id)
    if user:
        return jsonify(user)
    return jsonify({"error": "User not found"}), 404

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "user-watchlist-service"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)