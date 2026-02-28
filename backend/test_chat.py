import requests
import json

try:
    url = "http://127.0.0.1:5000/api/chat"
    payload = {"message": "What is my current power usage?"}
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(url, json=payload, headers=headers)
    print("Status Code:", response.status_code)
    print("Response JSON:")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print("Error:", e)
