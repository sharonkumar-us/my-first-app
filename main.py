import json
import urllib.request


def add_numbers(a, b):
    """Add two numbers and return the result."""
    return a + b


def fetch_url_json(url, timeout=10):
    """Fetch a URL and return the parsed JSON response."""
    with urllib.request.urlopen(url, timeout=timeout) as response:
        data = response.read()
    return json.loads(data.decode("utf-8"))

