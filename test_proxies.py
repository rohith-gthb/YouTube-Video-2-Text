import os
import random
import requests

PROXY_FILE = "backend/webshar_proxies.txt"

def get_random_proxy():
    if not os.path.exists(PROXY_FILE):
        return None
    with open(PROXY_FILE, 'r') as f:
        proxies = [line.strip() for line in f if line.strip()]
    if not proxies:
        return None
    proxy_raw = random.choice(proxies)
    parts = proxy_raw.split(':')
    if len(parts) == 4:
        ip, port, user, passw = parts
        proxy_url = f"http://{user}:{passw}@{ip}:{port}"
        return {"http": proxy_url, "https": proxy_url}
    return None

def test_proxies():
    print("Testing Proxies...")
    for i in range(5):
        proxies = get_random_proxy()
        try:
            r = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=5)
            print(f"Test {i+1} Result: {r.json()['ip']} (Success)")
        except Exception as e:
            print(f"Test {i+1} Failed: {e}")

if __name__ == "__main__":
    test_proxies()
