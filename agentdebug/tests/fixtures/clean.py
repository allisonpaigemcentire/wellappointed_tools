"""Invented module that should not trip agentdebug smell rules."""

import os


def check_order(items, max_steps=3):
    step = 0
    while step < max_steps:
        step += 1
        if not items:
            return False
    return False


def run_agent(client, prompt, max_turns=4):
    turn = 0
    while turn < max_turns:
        turn += 1
        client.chat.completions.create(
            model="demo",
            messages=[{"role": "user", "content": prompt}],
            timeout=30,
        )
    return False


def fetch_page(client):
    return client.get("https://example.invalid/page", timeout=5)


@retry(stop=stop_after_attempt(3))
def poll(client):
    return client.get("https://example.invalid/status", timeout=5)


@tool
def send_digest(channel, text, approved: bool = False):
    if not approved:
        raise RuntimeError("approval required")
    client.post(channel, text, timeout=5)


def configured_key():
    return os.environ["API_KEY"]


def keep_notes(notes):
    # A slice of an ordinary list is not a prompt truncation.
    return notes[:2]
