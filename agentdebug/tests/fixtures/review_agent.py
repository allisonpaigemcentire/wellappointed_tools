"""Invented agent from the review. Four real smells, plus three look-alikes that must stay quiet."""

import os, sys, requests
from openai import OpenAI

client = OpenAI(timeout=30)   # timeout set on the client
MAX_TOKENS = 512


def run(prompt):
    max_tokens = MAX_TOKENS
    while True:                                   # unbounded loop, should flag AGT003
        resp = client.chat.completions.create(model="m", messages=[{"role": "user", "content": prompt}], max_tokens=max_tokens)
        if resp.choices[0].finish_reason == "stop":
            return resp


def fetch_docs(url):
    try:
        return requests.get(url, timeout=5).json()
    except Exception:
        return []                                 # silent empty result, playbook section 11


class Agent:
    def __init__(self):
        self.http = requests.Session()

    def lookup(self, sku):
        return self.http.get(f"https://example.com/{sku}")   # no timeout, via self.*


def preview(text):
    print(text[:80])                              # log preview, not model input


def render_toolbar(items):
    sys.stdout.write(",".join(items))             # name contains 'tool'


def send_email_tool(to, body, confirm=False):
    if not confirm:
        raise PermissionError("needs approval")
    requests.post("https://example.com/send", json={"to": to}, timeout=5)


def poll_events(queue):
    while True:                                  # event loop with try/except, not a retry
        try:
            item = queue.get()
        except KeyError:
            continue
        handle(item)


API_KEY = os.environ.get("API_KEY", "sk-proj-abcdefghijklmnop1234")
