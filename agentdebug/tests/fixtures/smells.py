"""Invented module that should trip every agentdebug smell rule."""

import json


def load_notes(path):
    try:
        return open(path).read()
    except:
        return ""


def parse_notes(blob):
    try:
        return json.loads(blob)
    except ValueError:
        pass


def check_order(items):
    return True


def gate_report():
    return GatePass(passed=True, findings=[])


def run_agent(client, prompt):
    while True:
        clipped = prompt[:1200]
        client.chat.completions.create(
            model="demo",
            messages=[{"role": "user", "content": clipped}],
        )


def fetch_page(client):
    while True:
        try:
            return client.get("https://example.invalid/page")
        except ConnectionError:
            continue


@retry
def poll(client):
    return client.get("https://example.invalid/status")


@tool
def send_digest(channel, text):
    client.post(channel, text)


api_key = "local-only-static-string-0123456789"
