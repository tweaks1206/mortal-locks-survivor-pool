from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import json
import os

app = Flask(__name__)
CORS(app)

DATA_FILE = "survivor_data.json"
ADMIN_CODE = "9999"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"players": {}, "picks": {}, "results": {}, "eliminated": [], "buyback_used": [], "notifications": []}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    name = data.get('name', '').strip()
    code = data.get('code', '').strip()

    if not name or len(code) != 4 or not code.isdigit():
        return jsonify({"error": "Invalid credentials"}), 400

    pool_data = load_data()
    player_id = f"{name}_{code}"

    is_new_player = player_id not in pool_data["players"]
    if is_new_player:
        pool_data["players"][player_id] = {"name": name, "code": code, "joined": datetime.now().isoformat()}
        pool_data["notifications"].append({
            "id": len(pool_data["notifications"]),
            "type": "entry",
            "player_name": name,
            "amount": 25,
            "timestamp": datetime.now().isoformat(),
            "read": False
        })
        save_data(pool_data)

    return jsonify({"player_id": player_id, "name": name, "is_admin": code == ADMIN_CODE})

@app.route('/api/available-teams', methods=['POST'])
def available_teams():
    data = request.json or {}
    week = str(data.get('week', '1'))
    pool_data = load_data()

    used_teams = set()
    for pid, picks in pool_data["picks"].items():
        if week in picks:
            used_teams.add(picks[week])

    eliminated_teams = set()
    if week in pool_data["results"]:
        for game in pool_data["results"][week]:
            if game.get("loser"):
                eliminated_teams.add(game["loser"])

    all_teams = {
        "AFC": ["BAL", "BUF", "CLE", "DEN", "HOU", "IND", "JAX", "KC", "LAC", "LV", "MIA", "NE", "NYJ", "PIT", "TEN"],
        "NFC": ["ARI", "ATL", "CAR", "CHI", "DAL", "GB", "LAR", "MIN", "NO", "NYG", "PHI", "SEA", "SF", "TB", "WAS"]
    }

    available = {}
    for conf, teams in all_teams.items():
        available[conf] = [t for t in teams if t not in used_teams and t not in eliminated_teams]

    return jsonify(available)

@app.route('/api/make-pick', methods=['POST'])
def make_pick():
    data = request.json or {}
    player_id = data.get('player_id')
    week = str(data.get('week'))
    team = (data.get('team') or '').upper()

    if not player_id or not week or not team or len(team) < 2 or len(team) > 3:
        return jsonify({"error": "Invalid request"}), 400

    pool_data = load_data()
    if player_id not in pool_data["picks"]:
        pool_data["picks"][player_id] = {}

    pool_data["picks"][player_id][week] = team
    save_data(pool_data)

    return jsonify({"success": True})

@app.route('/api/standings', methods=['GET'])
def standings():
    pool_data = load_data()
    standings_data = []

    for player_id, player in pool_data["players"].items():
        picks = pool_data["picks"].get(player_id, {})
        win_count = len(picks)
        is_eliminated = player_id in pool_data["eliminated"]
        has_buyback = player_id not in pool_data["buyback_used"]

        standings_data.append({
            "name": player["name"],
            "wins": win_count,
            "eliminated": is_eliminated,
            "has_buyback": has_buyback
        })

    standings_data.sort(key=lambda x: (-x["wins"], x["eliminated"]))
    return jsonify(standings_data)

@app.route('/api/admin/set-result', methods=['POST'])
def set_result():
    data = request.json or {}

    if data.get('admin_code') != ADMIN_CODE:
        return jsonify({"error": "Unauthorized"}), 403

    week = str(data.get('week'))
    winner = (data.get('winner') or '').upper()
    loser = (data.get('loser') or '').upper()

    if not week or len(winner) != 2 or len(loser) != 2:
        return jsonify({"error": "Invalid teams"}), 400

    pool_data = load_data()
    if week not in pool_data["results"]:
        pool_data["results"][week] = []

    pool_data["results"][week].append({"winner": winner, "loser": loser})

    for player_id, picks in pool_data["picks"].items():
        if picks.get(week) == loser and player_id not in pool_data["eliminated"]:
            pool_data["eliminated"].append(player_id)

    save_data(pool_data)
    return jsonify({"success": True})

@app.route('/api/admin/buyback', methods=['POST'])
def buyback():
    data = request.json or {}

    if data.get('admin_code') != ADMIN_CODE:
        return jsonify({"error": "Unauthorized"}), 403

    player_id = data.get('player_id')
    pool_data = load_data()

    if player_id in pool_data["eliminated"]:
        pool_data["eliminated"].remove(player_id)
        if player_id not in pool_data["buyback_used"]:
            pool_data["buyback_used"].append(player_id)

        player_name = pool_data["players"].get(player_id, {}).get("name", player_id)
        pool_data["notifications"].append({
            "id": len(pool_data["notifications"]),
            "type": "buyback",
            "player_name": player_name,
            "amount": 10,
            "timestamp": datetime.now().isoformat(),
            "read": False
        })

        save_data(pool_data)
        return jsonify({"success": True})

    return jsonify({"error": "Player not eliminated"}), 400

@app.route('/api/admin/notifications', methods=['GET'])
def get_notifications():
    pool_data = load_data()
    return jsonify(pool_data.get("notifications", []))

@app.route('/api/admin/mark-notification-read', methods=['POST'])
def mark_notification_read():
    data = request.json or {}

    if data.get('admin_code') != ADMIN_CODE:
        return jsonify({"error": "Unauthorized"}), 403

    notification_id = data.get('notification_id')
    pool_data = load_data()

    for notif in pool_data.get("notifications", []):
        if notif.get("id") == notification_id:
            notif["read"] = True
            save_data(pool_data)
            return jsonify({"success": True})

    return jsonify({"error": "Notification not found"}), 404

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

if __name__ == '__main__':
    app.run(debug=False)
