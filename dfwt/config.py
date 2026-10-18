"""Loads config.json and resolves repository paths."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def path(*parts):
    return os.path.join(ROOT, *parts)


def load(config_path=None):
    with open(config_path or path("config.json"), encoding="utf-8") as f:
        return json.load(f)
