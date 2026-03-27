import os
import threading
import time
import random
import instaloader
import pyotp
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
CORS(app)

# Proxy list (free proxies - replace with your own if needed)
PROXY_LIST = [
    None,  # direct connection
    # Add more proxies if needed
]

processing = False
cancel_flag = False
results = []

@app.route('/')
def home():
    return jsonify({"status": "online", "message": "HBX Cookie Server Running", "proxy_count": len([p for p in PROXY_LIST if p])})

@app.route('/start', methods=['POST'])
def start():
    global processing, cancel_flag, results
    if processing:
        return jsonify({'status': 'error', 'message': 'Already processing'}), 400

    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'No data'}), 400

    usernames = data.get('usernames', [])
    password = data.get('password', '')
    keys = data.get('keys', [])
    use_proxy = data.get('use_proxy', True)

    if not usernames or not password or len(usernames) != len(keys):
        return jsonify({'status': 'error', 'message': 'Invalid input'}), 400

    processing = True
    cancel_flag = False
    results = []

    thread = threading.Thread(target=run_batch, args=(usernames, password, keys, use_proxy))
    thread.start()
    return jsonify({'status': 'ok', 'message': f'Processing {len(usernames)} accounts'})

@app.route('/status', methods=['GET'])
def status():
    global processing, results
    return jsonify({
        'processing': processing,
        'results': results if not processing else [],
        'count': len(results)
    })

@app.route('/cancel', methods=['POST'])
def cancel():
    global cancel_flag, processing
    if processing:
        cancel_flag = True
        return jsonify({'status': 'ok', 'message': 'Cancelled'})
    return jsonify({'status': 'error', 'message': 'Not processing'})

@app.route('/download', methods=['GET'])
def download():
    if not results:
        return jsonify({'status': 'error', 'message': 'No results'}), 400
    filename = f'cookies_{int(time.time())}.txt'
    with open(filename, 'w') as f:
        f.write('\n'.join(results))
    return send_file(filename, as_attachment=True)

def run_batch(usernames, password, keys, use_proxy):
    global processing, results, cancel_flag
    executor = ThreadPoolExecutor(max_workers=3)
    futures = []
    
    for i, (u, k) in enumerate(zip(usernames, keys)):
        if cancel_flag:
            break
        proxy = PROXY_LIST[i % len(PROXY_LIST)] if use_proxy and PROXY_LIST else None
        futures.append(executor.submit(login_worker, u, password, k, proxy))

    for f in futures:
        if cancel_flag:
            f.cancel()
        else:
            try:
                res = f.result()
                if res:
                    results.append(res)
            except Exception as e:
                print(f"Error: {e}")
    
    executor.shutdown(wait=False)
    processing = False

def login_worker(username, password, key, proxy):
    if cancel_flag:
        return None
    try:
        L = instaloader.Instaloader(quiet=True, max_connection_attempts=1)
        L.context._session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13) Instagram 269.0.0.18.78',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        
        if proxy:
            L.context._session.proxies = {'http': proxy, 'https': proxy}
        
        L.login(username, password)
        cookies = L.context._session.cookies.get_dict()
        cookie_str = '; '.join([f'{k}={v}' for k, v in cookies.items()])
        return f'{username}|{password}|{cookie_str}'
        
    except instaloader.exceptions.TwoFactorAuthRequiredException:
        try:
            totp = pyotp.TOTP(key.replace(' ', ''))
            L.two_factor_login(totp.now())
            cookies = L.context._session.cookies.get_dict()
            cookie_str = '; '.join([f'{k}={v}' for k, v in cookies.items()])
            return f'{username}|{password}|{cookie_str}'
        except Exception as e:
            return None
    except Exception as e:
        return None

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
