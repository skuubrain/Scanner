import time
import requests
import json
from collections import defaultdict
from datetime import datetime
import pandas as pd

# --- HARDCODED API KEYS ---
HELIUS_API_KEY = "77ded072-5330-4df7-b26f-b59c419499c4"
ALCHEMY_API_KEYS = ["NuBdUiCxSiGRTuHzQRcFz", "dw_ir0Yc-E-vOKQaWep19"]

HELIUS_BASE_URL = "https://mainnet.helius-rpc.com"
ALCHEMY_BASE_URL = "https://solana-mainnet.g.alchemy.com/v2"

TOP_TRADERS_LIMIT = 100
LOOKBACK_SECONDS = 6 * 60 * 60
MIN_WALLETS_FOR_SIGNAL = 2
REQUEST_DELAY = 0.5

alchemy_key_index = 0

def get_alchemy_key():
    global alchemy_key_index
    k = ALCHEMY_API_KEYS[alchemy_key_index % len(ALCHEMY_API_KEYS)]
    alchemy_key_index += 1
    return k

def helius_rpc_call(method, params=[]):
    url = f"{HELIUS_BASE_URL}/?api-key={HELIUS_API_KEY}"
    payload = {"jsonrpc": "2.0", "id": "1", "method": method, "params": params}
    try:
        r = requests.post(url, json=payload, timeout=30)
        return r.json().get("result", {}) if r.status_code == 200 else {}
    except:
        return {}

def alchemy_rpc_call(method, params=[]):
    for _ in range(len(ALCHEMY_API_KEYS) * 2):
        key = get_alchemy_key()
        url = f"{ALCHEMY_BASE_URL}/{key}"
        payload = {"jsonrpc": "2.0", "id": "1", "method": method, "params": params}
        try:
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                return r.json().get("result", {})
        except:
            pass
        time.sleep(0.5)
    return {}

def get_signatures_for_address(address, limit=100):
    result = alchemy_rpc_call("getSignaturesForAddress", [address, {"limit": limit}])
    return result if isinstance(result, list) else []

def get_transaction(signature):
    result = alchemy_rpc_call("getTransaction", [
        signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
    ])
    return result

def get_token_accounts_by_owner(owner, program_id="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"):
    result = alchemy_rpc_call("getTokenAccountsByOwner", [owner, {"programId": program_id}, {"encoding": "jsonParsed"}])
    return result.get("value", []) if isinstance(result, dict) else []

def get_token_metadata_helius(mint_address):
    url = f"{HELIUS_BASE_URL}/?api-key={HELIUS_API_KEY}"
    payload = {"jsonrpc": "2.0", "id": "1", "method": "getAsset", "params": {"id": mint_address}}
    try:
        r = requests.post(url, json=payload, timeout=30)
        return r.json().get("result", {}) if r.status_code == 200 else None
    except:
        return None

def get_token_creation_time(mint_address):
    signatures = helius_rpc_call("getSignaturesForAddress", [mint_address, {"limit": 1000}])
    if not signatures or not isinstance(signatures, list):
        return None
    earliest_sig = signatures[-1]
    if isinstance(earliest_sig, dict):
        return earliest_sig.get("blockTime")
    return None

def parse_transaction_for_token_buys(tx_data, wallet_address):
    purchases = []
    if not tx_data or "blockTime" not in tx_data:
        return purchases
    block_time = tx_data.get("blockTime")
    timestamp = datetime.fromtimestamp(block_time).strftime("%Y-%m-%d %H:%M:%S") if block_time else "Unknown"
    meta = tx_data.get("meta", {})
    pre_balances = meta.get("preTokenBalances", [])
    post_balances = meta.get("postTokenBalances", [])
    pre_token_map = {b.get("mint"): float(b.get("uiTokenAmount", {}).get("uiAmount", 0))
                     for b in pre_balances if b.get("owner") == wallet_address and b.get("mint")}
    for balance in post_balances:
        if balance.get("owner") != wallet_address or not balance.get("mint"):
            continue
        mint = balance["mint"]
        post_amount = float(balance.get("uiTokenAmount", {}).get("uiAmount", 0))
        pre_amount = pre_token_map.get(mint, 0)
        if post_amount > pre_amount:
            purchases.append({"token": mint, "timestamp": timestamp, "block_time": block_time, "amount_increase": post_amount - pre_amount})
    return purchases

def scan_wallet_for_buys(wallet_address, lookback_seconds=LOOKBACK_SECONDS):
    print(f"Scanning wallet: {wallet_address[:8]}...")
    signatures = get_signatures_for_address(wallet_address, limit=50)
    token_purchases = []
    current_time = time.time()
    for sig_info in signatures:
        if not isinstance(sig_info, dict):
            continue
        block_time = sig_info.get("blockTime")
        if not block_time or block_time < (current_time - lookback_seconds):
            continue
        signature = sig_info.get("signature")
        if not signature:
            continue
        tx_data = get_transaction(signature)
        if tx_data:
            token_purchases.extend(parse_transaction_for_token_buys(tx_data, wallet_address))
        time.sleep(REQUEST_DELAY)
    return token_purchases

def generate_scan(wallet_list=None):
    print("Starting Solana scanner...")
    if not wallet_list:
        wallet_list = ["GrDMoeqMLFjeXQ24H56S1RLgT4R76jsuWCd6SvXyGPQ5", "2ojv9BAiHUrvsm9gxDe7fJSzbNZSJcxZvf8dqmWGHG8S"]
    token_to_wallets = defaultdict(lambda: {"wallets": {}, "earliest_time": None})
    for i, wallet in enumerate(wallet_list):
        print(f"Scanning wallet {i+1}/{len(wallet_list)}")
        purchases = scan_wallet_for_buys(wallet)
        for p in purchases:
            token_data = token_to_wallets[p["token"]]
            token_data["wallets"][wallet] = {"purchase_time": p["timestamp"], "block_time": p["block_time"]}
            if token_data["earliest_time"] is None or p["block_time"] < token_data["earliest_time"]:
                token_data["earliest_time"] = p["block_time"]
    candidates = []
    for token, data in token_to_wallets.items():
        wallets_dict = data.get("wallets", {})
        wallet_count = len(wallets_dict)
        if wallet_count >= MIN_WALLETS_FOR_SIGNAL:
            token_creation_timestamp = get_token_creation_time(token) or data.get("earliest_time")
            token_created_time = datetime.fromtimestamp(token_creation_timestamp).strftime("%Y-%m-%d %H:%M:%S") if token_creation_timestamp else "Unknown"
            candidates.append({"token": token, "wallet_count": wallet_count, "token_first_seen": token_created_time, "token_timestamp": token_creation_timestamp, "wallets": wallets_dict})
    candidates.sort(key=lambda x: x["wallet_count"], reverse=True)
    with open("copurchase_signals.json", "w") as f:
        json.dump(candidates, f, indent=2)
    df_records = [{"token": e["token"], "wallet": w, "purchase_time": wd["purchase_time"], "token_first_seen": e["token_first_seen"], "total_wallets": e["wallet_count"]} for e in candidates for w, wd in e["wallets"].items()]
    if df_records:
        pd.DataFrame(df_records).to_csv("copurchase_signals.csv", index=False)
    print(f"Scan complete! {len(candidates)} tokens found with {MIN_WALLETS_FOR_SIGNAL}+ wallets.")
    return candidates

def check_wallet_holdings(wallet, token):
    for account in get_token_accounts_by_owner(wallet):
        parsed = account.get("account", {}).get("data", {}).get("parsed", {})
        info = parsed.get("info", {})
        mint = info.get("mint")
        amount = info.get("tokenAmount", {}).get("uiAmount", 0)
        if mint == token and amount > 0:
            return True
    return False

def check_token_holdings(token, wallets_data):
    holdings_status = {}
    for wallet, info in wallets_data.items():
        still_holding = check_wallet_holdings(wallet, token)
        holdings_status[wallet] = {"still_holding": still_holding, "status": "HOLDING" if still_holding else "SOLD", "purchase_time": info.get("purchase_time", "Unknown")}
        time.sleep(0.5)
    holders = sum(1 for w in holdings_status.values() if w["still_holding"])
    sellers = len(wallets_data) - holders
    print(f"Holdings check complete: {holders} holding, {sellers} sold")
    return {"total_wallets": len(wallets_data), "still_holding": holders, "sold": sellers, "wallets": holdings_status}

if __name__ == "__main__":
    generate_scan()
