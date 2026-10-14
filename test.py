
import os
import requests

API_KEY = "sk-5ea7d370d0f645a19e719f9b42cc7a78"

url = "https://api.deepseek.com/user/balance"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}

response = requests.get(url, headers=headers, timeout=30)

if response.status_code == 200:
    data = response.json()

    for balance in data.get("balance_infos", []):
        print(f"Currency: {balance.get('currency')}")
        print(f"Total balance: {balance.get('total_balance')}")
        print(f"Granted balance: {balance.get('granted_balance')}")
        print(f"Topped-up balance: {balance.get('topped_up_balance')}")
        print("-" * 30)
else:
    print(f"Error: {response.status_code}")
    print(response.text)
