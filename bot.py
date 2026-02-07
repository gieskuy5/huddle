import requests
import time
import random
import threading
import asyncio
from datetime import datetime, timezone
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

Account.enable_unaudited_hdwallet_features()

# ============== CONFIGURATION ==============
JOIN_DURATION_HOURS = 3   # Duration to stay in room
COOLDOWN_HOURS = 24       # Cooldown between cycles

# ============== COLORS ==============
R = '\033[0m'    # Reset
G = '\033[92m'   # Green
Y = '\033[93m'   # Yellow
C = '\033[96m'   # Cyan
M = '\033[95m'   # Magenta
RED = '\033[91m' # Red

# ============== NAMES ==============
NAMES = ["James", "John", "Robert", "Michael", "David", "William", "Emma", "Olivia", "Sophia", "Liam", "Noah", "Oliver", "Lucas", "Mason", "Logan", "Ethan", "Daniel", "Henry", "Jack", "Ryan"]

def random_name():
    return f"{random.choice(NAMES)}{random.randint(10,99)}"

def fingerprint():
    return {
        "sec-ch-ua": '"Chromium";v="130", "Google Chrome";v="130"',
        "sec-ch-ua-platform": '"Windows"',
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"
    }

def fmt_time(sec):
    h, m, s = int(sec//3600), int((sec%3600)//60), int(sec%60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def short_wallet(w):
    return f"{w[:8]}...{w[-6:]}" if w else "N/A"

# ============== LIVE ROOM ==============
def join_room(session, pk, room_id, fp):
    try:
        acc = Account.from_key(pk)
        wallet = Web3.to_checksum_address(acc.address)
        headers = {
            "accept": "*/*", "content-type": "application/json",
            "sec-ch-ua": fp["sec-ch-ua"], "sec-ch-ua-platform": fp["sec-ch-ua-platform"],
            "user-agent": fp["user-agent"], "origin": "https://huddle01.app"
        }
        
        # Generate challenge
        r = session.post("https://huddle01.app/api/v2/platform/api/v2/auth/wallet/generateChallenge",
                        headers=headers, json={"walletAddress": wallet}, timeout=30)
        if r.status_code != 200 or not r.json().get("ok"):
            return wallet, None, "challenge_fail"
        
        signing_msg = r.json().get("signingMessage")
        sig = "0x" + acc.sign_message(encode_defunct(text=signing_msg)).signature.hex()
        
        # Login
        r = session.post("https://huddle01.app/api/v2/platform/api/v2/auth/wallet/login",
                        headers=headers, json={"address": wallet, "signature": sig, "chain": "eth", "wallet": "metamask", "dashboardType": "personal"}, timeout=30)
        if r.status_code != 200 or not r.json().get("ok"):
            return wallet, None, "login_fail"
        
        token = r.json().get("tokens", {}).get("accessToken")
        headers["authorization"] = f"Bearer {token}"
        
        # Token gating
        r = session.get(f"https://huddle01.app/api/v2/platform/api/v2/tokenGating?roomId={room_id}&lensAccessToken=", headers=headers, timeout=30)
        if r.status_code != 200 or not r.json().get("auth"):
            return wallet, None, "denied"
        
        # Create meeting token
        name = random_name()
        r = session.post("https://huddle01.app/api/v2/platform/api/v2/create-meeting-token",
                        headers=headers, json={"roomId": room_id, "metadata": {"displayName": name, "walletAddress": wallet}}, timeout=30)
        if r.status_code != 200:
            return wallet, None, "token_fail"
        
        meeting_token = r.json().get("token")
        return wallet, meeting_token, "ok"
    except Exception as e:
        return None, None, str(e)[:20]

def keep_alive(session, room_id, wallet, token, stop_event, info):
    info['status'] = 'JOINED'
    info['join_time'] = time.time()
    headers = {"authorization": f"Bearer {token}"}
    
    while not stop_event.is_set():
        try:
            session.get(f"https://huddle01.app/api/v2/platform/api/v2/web/getPreviewPeersInternal/{room_id}", headers=headers, timeout=30)
            for _ in range(30):
                if stop_event.is_set(): break
                time.sleep(1)
        except:
            time.sleep(10)

def process_live(pk, room_id, idx, infos, stop_event):
    info = infos[idx]
    session = requests.Session()
    fp = fingerprint()
    
    wallet, token, status = join_room(session, pk, room_id, fp)
    info['wallet'] = wallet
    
    if status != "ok":
        info['status'] = status.upper()
        return
    
    info['status'] = 'CONNECTING'
    keep_alive(session, room_id, wallet, token, stop_event, info)
    info['status'] = 'LEFT'

# ============== CLAIM MISSIONS ==============
def claim_meet(pk):
    session = requests.Session()
    fp = fingerprint()
    headers = {
        "accept": "*/*", "content-type": "application/json",
        "sec-ch-ua": fp["sec-ch-ua"], "x-trpc-source": "nextjs-react",
        "user-agent": fp["user-agent"]
    }
    
    try:
        acc = Account.from_key(pk)
        wallet = Web3.to_checksum_address(acc.address)
        
        # Get nonce
        r = session.post("https://testnet.huddle01.com/api/trpc/auth.nonce?batch=1",
                        headers=headers, json={"0": {"json": None, "meta": {"values": ["undefined"]}}}, timeout=30)
        if r.status_code != 200:
            return wallet, False, 0, "nonce_fail"
        
        nonce = r.json()[0].get('result', {}).get('data', {}).get('json')
        issued_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        
        message = f"testnet.huddle01.com wants you to sign in with your Ethereum account:\n{wallet}\n\nSign in with Ethereum\n\nURI: https://testnet.huddle01.com\nVersion: 1\nChain ID: 2524852\nNonce: {nonce}\nIssued At: {issued_at}"
        sig = "0x" + acc.sign_message(encode_defunct(text=message)).signature.hex()
        
        # Login
        r = session.post("https://testnet.huddle01.com/api/trpc/auth.login?batch=1",
                        headers=headers, json={"0": {"json": {"message": message, "signature": sig}}}, timeout=30)
        if r.status_code != 200 or not r.json()[0].get('result', {}).get('data', {}).get('json'):
            return wallet, False, 0, "login_fail"
        
        # Get missions
        r = session.get("https://testnet.huddle01.com/api/trpc/quests.all,quests.stream?batch=1&input=%7B%220%22%3A%7B%22json%22%3A%7B%22filters%22%3A%7B%22category%22%3A%5B%22SPARTANS%22%2C%22KEEPERS%22%2C%22CREATORS%22%2C%22EXPLORERS%22%5D%2C%22searchQuery%22%3A%22%22%2C%22isCompleted%22%3Afalse%2C%22hpSort%22%3Anull%7D%7D%2C%22meta%22%3A%7B%22values%22%3A%7B%22filters.hpSort%22%3A%5B%22undefined%22%5D%7D%7D%7D%2C%221%22%3A%7B%22json%22%3Anull%2C%22meta%22%3A%7B%22values%22%3A%5B%22undefined%22%5D%7D%7D%7D",
                       headers=headers, timeout=30)
        
        quests = r.json()[0].get('result', {}).get('data', {}).get('json', [])
        for q in quests:
            if q.get('questKey') == 'meet':
                hp = q.get('hpAwarded', 0)
                if hp and int(str(hp)) > 0:
                    # Claim
                    r = session.post("https://testnet.huddle01.com/api/trpc/quests.completeQuest?batch=1",
                                    headers=headers, json={"0": {"json": {"isRepeatable": True, "questKey": "meet"}}}, timeout=30)
                    result = r.json()[0].get('result', {}).get('data', {}).get('json', {})
                    points = result.get('points', 0)
                    mins = result.get('meetMins', 0)
                    if points > 0:
                        return wallet, True, points, f"+{points}pts ({mins}m)"
                    return wallet, False, 0, "no_points"
                return wallet, True, 0, "nothing_to_claim"
        return wallet, False, 0, "quest_not_found"
    except Exception as e:
        return None, False, 0, str(e)[:20]

# ============== DISPLAY ==============
def display_live(infos, stop_event, start_time, duration_h):
    target = duration_h * 3600
    
    while not stop_event.is_set():
        print("\033[H\033[J", end="")
        
        elapsed = time.time() - start_time
        remaining = max(0, target - elapsed)
        joined = sum(1 for i in infos if i['status'] == 'JOINED')
        
        print(f"{C}═══════════════════════════════════════════════════════════{R}")
        print(f"{C}  HUDDLE01 AUTO JOIN + CLAIM{R}")
        print(f"{C}═══════════════════════════════════════════════════════════{R}")
        print(f"  {Y}Time:{R} {datetime.now().strftime('%H:%M:%S')}  {Y}Elapsed:{R} {fmt_time(elapsed)}  {Y}Remaining:{R} {fmt_time(remaining)}")
        print(f"  {Y}Joined:{R} {G}{joined}{R}/{len(infos)}")
        print(f"{C}───────────────────────────────────────────────────────────{R}")
        print(f"  {'#':<3} {'Wallet':<20} {'Status':<15} {'Duration':<10}")
        print(f"{C}───────────────────────────────────────────────────────────{R}")
        
        for i, info in enumerate(infos, 1):
            dur = fmt_time(time.time() - info['join_time']) if info['join_time'] else "--:--:--"
            status = info['status']
            color = G if status == 'JOINED' else RED if 'FAIL' in status.upper() else Y
            print(f"  {i:<3} {short_wallet(info['wallet']):<20} {color}{status:<15}{R} {dur:<10}")
        
        print(f"{C}───────────────────────────────────────────────────────────{R}")
        print(f"  {Y}Press Ctrl+C to stop{R}")
        time.sleep(1)

def display_cooldown(end_time):
    while time.time() < end_time:
        remaining = end_time - time.time()
        print("\033[H\033[J", end="")
        print(f"{C}═══════════════════════════════════════════════════════════{R}")
        print(f"{C}  HUDDLE01 - COOLDOWN{R}")
        print(f"{C}═══════════════════════════════════════════════════════════{R}")
        print(f"  {Y}Next cycle in:{R} {G}{fmt_time(remaining)}{R}")
        print(f"  {Y}Next run:{R} {datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{C}═══════════════════════════════════════════════════════════{R}")
        time.sleep(1)

# ============== MAIN ==============
def main():
    print(f"""
{C}  __ __  __ __  ___    ___    _        ___ 
 |  |  ||  |  ||   \\  |   \\  | |      /  _]
 |  |  ||  |  ||    \\ |    \\ | |     /  [_ 
 |  _  ||  |  ||  D  ||  D  || |___ |    _]
 |  |  ||  :  ||     ||     ||     ||   [_ 
 |  |  ||     ||     ||     ||     ||     |
 |__|__| \\__,_||_____||_____||_____||_____|{R}
                                          
{Y}         https://t.me/MDFKOfficial{R}
""")
    
    # Read keys
    try:
        with open('privkey.txt', 'r') as f:
            keys = [l.strip() for l in f if l.strip()]
    except:
        print(f"{RED}  ✗ privkey.txt not found{R}")
        return
    
    print(f"  {Y}Accounts:{R} {len(keys)}")
    print(f"  {Y}WebSocket:{R} {'Yes' if HAS_WEBSOCKETS else 'No (HTTP fallback)'}")
    
    # Get room
    print(f"\n  {Y}Enter room link:{R}")
    room_link = input(f"  {G}> {R}").strip()
    
    if "/room/" not in room_link:
        print(f"{RED}  ✗ Invalid room link{R}")
        return
    
    room_id = room_link.split("/room/")[1].split("/")[0].split("?")[0]
    print(f"  {Y}Room ID:{R} {room_id}\n")
    
    cycle = 1
    while True:
        # ===== PHASE 1: JOIN =====
        print(f"\n{M}━━━ CYCLE {cycle} ━━━{R}")
        print(f"\n{G}▶ PHASE 1: Joining room ({JOIN_DURATION_HOURS}h){R}")
        
        infos = [{'wallet': None, 'status': 'WAITING', 'join_time': None} for _ in keys]
        stop_event = threading.Event()
        start_time = time.time()
        
        # Display thread
        disp = threading.Thread(target=display_live, args=(infos, stop_event, start_time, JOIN_DURATION_HOURS), daemon=True)
        disp.start()
        
        # Account threads
        for i, pk in enumerate(keys):
            t = threading.Thread(target=process_live, args=(pk, room_id, i, infos, stop_event), daemon=True)
            t.start()
            time.sleep(random.uniform(1, 3))
        
        # Wait
        try:
            end_time = start_time + (JOIN_DURATION_HOURS * 3600)
            while time.time() < end_time:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        
        stop_event.set()
        time.sleep(2)
        
        # Summary
        joined = sum(1 for i in infos if i['join_time'])
        print(f"\n{C}───────────────────────────────────────────────────────────{R}")
        print(f"  {G}✓ Join complete:{R} {joined}/{len(keys)} accounts")
        print(f"  {Y}Duration:{R} {fmt_time(time.time() - start_time)}")
        
        # ===== PHASE 2: CLAIM =====
        print(f"\n{G}▶ PHASE 2: Claiming Meet-2-Earn{R}")
        print(f"{C}───────────────────────────────────────────────────────────{R}")
        
        total_pts = 0
        for i, pk in enumerate(keys, 1):
            wallet, success, pts, msg = claim_meet(pk)
            total_pts += pts
            status = f"{G}✓{R}" if success else f"{RED}✗{R}"
            print(f"  {i}. {short_wallet(wallet)} {status} {msg}")
            time.sleep(random.uniform(0.5, 1.5))
        
        print(f"{C}───────────────────────────────────────────────────────────{R}")
        print(f"  {G}Total points claimed:{R} +{total_pts}")
        
        # ===== PHASE 3: COOLDOWN =====
        print(f"\n{G}▶ PHASE 3: Cooldown ({COOLDOWN_HOURS}h){R}")
        
        try:
            display_cooldown(time.time() + (COOLDOWN_HOURS * 3600))
        except KeyboardInterrupt:
            print(f"\n{Y}  Stopped by user{R}")
            break
        
        cycle += 1

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Y}Stopped{R}")
