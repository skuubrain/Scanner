from flask import Flask, render_template, jsonify, redirect, url_for, request
import json
import os
from datetime import datetime
from scanner import generate_scan, check_token_holdings
from custom_tracker import (
    add_custom_wallet, 
    remove_custom_wallet, 
    get_custom_wallets,
    scan_custom_wallets,
    get_custom_tracker_results,
    check_custom_wallet_holdings
)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', 'dev-secret-key-change-in-production')

@app.route("/")
def home():
    results = {}
    last_scan = "Never"

    if os.path.exists("copurchase_signals.json"):
        try:
            with open("copurchase_signals.json", "r") as f:
                data = json.load(f)
                for entry in data:
                    token = entry.get("token")
                    wallets_data = entry.get("wallets", {})
                    token_first_seen = entry.get("token_first_seen", "Unknown")
                    
                    results[token] = {
                        "wallet_count": len(wallets_data),
                        "wallets": wallets_data,
                        "token_first_seen": token_first_seen
                    }
                last_scan = datetime.fromtimestamp(os.path.getmtime("copurchase_signals.json")).strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            print(f"Error loading results: {e}")
            pass

    custom_wallets = get_custom_wallets()
    custom_results = get_custom_tracker_results()

    return render_template("index.html", 
                         results=results, 
                         last_scan=last_scan,
                         custom_wallets=custom_wallets,
                         custom_results=custom_results)

@app.route("/scan")
def scan():
    generate_scan()
    return redirect(url_for('home'))

@app.route("/api/scan")
def api_scan():
    data = generate_scan()
    return jsonify({"status": "success", "tokens_found": len(data), "data": data})

@app.route("/check_holdings/<token>")
def check_holdings(token):
    if not os.path.exists("copurchase_signals.json"):
        return jsonify({"error": "No scan data found"}), 404

    with open("copurchase_signals.json", "r") as f:
        data = json.load(f)

    token_data = None
    for entry in data:
        if entry.get("token") == token:
            token_data = entry
            break

    if not token_data:
        return jsonify({"error": "Token not found"}), 404

    wallets = token_data.get("wallets", {})
    result = check_token_holdings(token, wallets)
    result["token"] = token

    return jsonify(result)

@app.route("/api/custom_wallets", methods=["GET", "POST", "DELETE"])
def custom_wallets_api():
    if request.method == "GET":
        wallets = get_custom_wallets()
        return jsonify({"success": True, "wallets": wallets})
    
    elif request.method == "POST":
        data = request.get_json()
        wallet_address = data.get("address", "").strip() if data else ""
        wallet_name = data.get("name", "").strip() if data else ""
        
        if not wallet_address:
            return jsonify({"success": False, "message": "Wallet address is required"}), 400
        
        result = add_custom_wallet(wallet_address, wallet_name)
        return jsonify(result)
    
    elif request.method == "DELETE":
        data = request.get_json()
        wallet_address = data.get("address", "").strip() if data else ""
        
        if not wallet_address:
            return jsonify({"success": False, "message": "Wallet address is required"}), 400
        
        result = remove_custom_wallet(wallet_address)
        return jsonify(result)
    
    return jsonify({"success": False, "message": "Invalid request method"}), 400

@app.route("/api/scan_custom_wallets")
def scan_custom_wallets_api():
    lookback_hours = request.args.get("lookback_hours", 6, type=int)
    lookback_seconds = lookback_hours * 60 * 60
    
    result = scan_custom_wallets(lookback_seconds)
    return jsonify(result)

@app.route("/api/custom_tracker_results")
def custom_tracker_results_api():
    results = get_custom_tracker_results()
    return jsonify({"success": True, "results": results})

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
