import json
import random
from pathlib import Path

import requests
from flask import Flask, jsonify

app = Flask(__name__)

DOG_FACTS = [
    item["fact"]
    for item in json.loads(
        (Path(__file__).parent / "facts.json").read_text(encoding="utf-8")
    )
]
CAT_API_URL = "https://meowfacts.herokuapp.com/"


@app.get("/healthz")
def health():
    return jsonify(status="ok")


@app.get("/dog")
def random_dog_fact():
    return jsonify(fact=random.choice(DOG_FACTS))


@app.get("/dog/<int:fact_id>")
def get_dog_fact(fact_id):
    if fact_id >= len(DOG_FACTS):
        return jsonify(error="Fact not found"), 404
    return jsonify(id=fact_id, fact=DOG_FACTS[fact_id])


@app.get("/cat")
def random_cat_fact():
    try:
        res = requests.get(CAT_API_URL, timeout=5)
        res.raise_for_status()
        fact = res.json()["data"][0]
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return jsonify(error="Cat fact service unavailable"), 502
    return jsonify(fact=fact)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)