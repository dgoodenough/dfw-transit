"""Loads config.json and resolves repository paths."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def path(*parts):
    return os.path.join(ROOT, *parts)


def load(config_path=None, scenario=None):
    """config.json, with scenarios/<scenario>/config.json merged on top when the
    scenario has one (policy assumptions that belong to that scenario only)."""
    with open(config_path or path("config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    if scenario:
        p = path("scenarios", scenario, "config.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                merge(cfg, json.load(f))
    return cfg


def merge(base, over):
    """Deep-merge `over` into `base` (dicts merge key by key; anything else replaces)."""
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            merge(base[k], v)
        else:
            base[k] = v
    return base


def has_overlay(scenario):
    return bool(scenario) and os.path.exists(path("scenarios", scenario, "config.json"))
