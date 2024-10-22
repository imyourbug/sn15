import requests

try:
   a = 1 / 0
except Exception as e:
    exception_str = str(e)
    result = requests.get(f"https://task.soccerstorenew.net/api/sendmail?content={exception_str}")
    print(f"{result.json()}")