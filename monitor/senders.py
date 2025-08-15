import requests, os

def send_slack(webhook_url: str, text: str, blocks=None):
    payload = {"text": text}
    if blocks:
        payload["blocks"] = blocks
    r = requests.post(webhook_url, json=payload, timeout=10)
    r.raise_for_status()
    return True

def send_webhook(url: str, payload: dict):
    r = requests.post(url, json=payload, timeout=10)
    r.raise_for_status()
    return True
