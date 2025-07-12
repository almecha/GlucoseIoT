# este es el codigo que le tira alertas via REST al telegram bot
import requests
payload = {
    "userID": 5925787255,  # from Telegram
    "alert": "Glucose too low",
    "action": "Eat a banana 🍌"
}
res = requests.post("http://localhost:9080", json=payload)
print(res.json())

