import urllib.request
import json

data = json.dumps({"message": "status"}).encode("utf-8")
req = urllib.request.Request("http://127.0.0.1:5000/api/chat", data=data, headers={"Content-Type": "application/json"})
res = urllib.request.urlopen(req)
print(res.read().decode("utf-8"))
