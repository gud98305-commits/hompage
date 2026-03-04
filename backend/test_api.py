import requests

url = "http://localhost:8000/api/chat"
headers = {"Content-Type": "application/json"}
data = {
    "user_id": "test",
    "message": "추천해",
    "user_meta": {"body_type": "straight"},
    "history": []
}

response = requests.post(url, headers=headers, json=data)
print("Status Code:", response.status_code)
print("Response JSON:", response.json())
