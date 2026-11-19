"""Public CI validates synthetic frozen service outputs without private code."""
import hashlib
import json
from pathlib import Path
import unittest

from core.multi_asset.adapters import validate_request
from core.multi_asset.service import validate_result
from multi_asset_fixture import make_request

FIXTURES = Path(__file__).parent/'fixtures/multi_asset'


class FrozenFixtureTests(unittest.TestCase):
    def test_frozen_results_bind_to_exact_synthetic_requests(self):
        request = make_request()
        for name in ('accumulation', 'income', 'missing'):
            if name == 'income':
                request['objective'] = 'income'
            if name == 'missing':
                request['observations'][0]['value'] = None
                request['cash_flow_assumptions']['withholding_tax_rate'] = None
                request['holdings'] = []
            with self.subTest(name=name):
                raw = (FIXTURES/f'{name}.request.json').read_bytes()
                self.assertEqual(json.loads(raw), request)
                validate_request(request)
                result = json.loads((FIXTURES/f'{name}.result.json').read_text(encoding='utf-8'))
                validate_result(result, request, hashlib.sha256(raw).hexdigest())
                self.assertIn('SYNTHETIC TEST ONLY', request['adapter_lineage']['notice'])
