"""Canonical SYNTHETIC TEST ONLY input, shared unchanged across operating systems.

The frozen file is authoritative. Recomputing trigonometric seed values on each
platform would introduce libm roundoff differences and break input-byte hashes.
None of these quotes, distributions or weights are market evidence.
"""
import json
from pathlib import Path


def make_request():
    path = Path(__file__).parent / 'fixtures/multi_asset/accumulation.request.json'
    return json.loads(path.read_text(encoding='utf-8'))
