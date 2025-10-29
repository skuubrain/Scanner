import json
import os
from datetime import datetime
import asyncio
import aiohttp
from scanner import scan_wallet_for_buys, check_wallet_holdings  # reuse your main scanner functions

CUSTOM_WALLETS_FILE = "custom_tracked_wallets.json"
CUSTOM_TRACKER_RESULTS = "custom_tracker_results.json"

# --- Wallet Storage Functions ---
def load_custom_wallets():
    if os.path.exists(CUSTOM_WALLETS_FILE):
        try:
            with open(CUSTOM_WALLETS_FILE, "r") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except:
            return []
    return []

def save_custom_wallets(wallets):
    with open(CUSTOM_WALLETS_FILE, "w") as f:
        json.dump(wallets, f, indent=2)

def add_custom_wallet(wallet_address, name=""):
    wallets = load_custom_wallets()
    if any(w.get("address") == wallet_address for w in wallets):
        return {"success": False, "message": "Wallet already in tracking list"}
    wallets.append({
        "address": wallet_address,
        "name": name or f"Wallet {len(wallets)+1}",
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_custom_wallets(wallets)
    return {"success": True, "message": "Wallet added successfully", "wallets": wallets}

def remove_custom_wallet(wallet_address):
    wallets = load_custom_wallets()
    original_count = len(wallets)
    wallets = [w for w in wallets if w.get("address") != wallet_address]
    if len(wallets) == original_count:
        return {"success": False, "message": "Wallet not found in tracking list"}
    save_custom_wallets(wallets)
    return {"success": True, "message": "Wallet removed successfully", "wallets": wallets}

def get_custom_wallets():
    return load_custom_wallets()

# --- Async Scanning ---
async def scan_wallet(session, wallet_info, lookback_seconds=6*60*60):
    wallet_address = wallet_info.get("address")
    wallet_name = wallet_info.get("name", "Unknown")
    print(f"  📊 Scanning {wallet_name}: {wallet_address[:8]}...")

    # Run the original scan_wallet_for_buys in a thread to not block the event loop
    loop = asyncio.get_running_loop()
    purchases = await loop.run_in_executor(None, scan_wallet_for_buys, wallet_address, lookback_seconds)

    token_summary = {}
    for purchase in purchases:
        token = purchase["token"]
        if token not in token_summary:
            token_summary[token] = {
                "token": token,
                "first_purchase": purchase["timestamp"],
                "first_purchase_time": purchase["block_time"],
                "total_buys": 0
            }
        token_summary[token]["total_buys"] += 1

    return {
        "wallet_address": wallet_address,
        "wallet_name": wallet_name,
        "tokens_bought": list(token_summary.values()),
        "total_tokens": len(token_summary),
        "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

async def scan_custom_wallets_async(lookback_seconds=6*60*60):
    wallets = load_custom_wallets()
    if not wallets:
        return {"success": False, "message": "No custom wallets to scan", "results": []}

    print(f"🔍 Scanning {len(wallets)} custom wallets...")

    results = []
    async with aiohttp.ClientSession() as session:
        tasks = [scan_wallet(session, w, lookback_seconds) for w in wallets]
        results = await asyncio.gather(*tasks)

    with open(CUSTOM_TRACKER_RESULTS, "w") as f:
        json.dump(results, f, indent=2)

    print(f"✅ Custom wallet scan complete!")
    return {"success": True, "message": "Scan completed", "results": results}

# --- Holdings Check ---
def check_custom_wallet_holdings(wallet_address, token):
    return check_wallet_holdings(wallet_address, token)

def get_custom_tracker_results():
    if os.path.exists(CUSTOM_TRACKER_RESULTS):
        try:
            with open(CUSTOM_TRACKER_RESULTS, "r") as f:
                return json.load(f)
        except:
            return []
    return []

# --- Entry point for async scan ---
def scan_custom_wallets(lookback_seconds=6*60*60):
    return asyncio.run(scan_custom_wallets_async(lookback_seconds))
