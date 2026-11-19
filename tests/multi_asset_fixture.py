"""Synthetic TEST ONLY inputs for offline arithmetic, integration and screenshots.

No prices, yield values, manager records or exposure weights here are market facts.
"""
from datetime import date
import math


def make_request():
    grid = [date(2023 + n//12, n % 12 + 1, 1).isoformat() for n in range(36)]
    def provenance(period):
        return dict(published_at=period+'T23:00:00Z', acquired_at=period+'T23:00:00Z',
            source_url='https://example.org/synthetic-test-only', snapshot_id='TEST-ONLY-v1')
    instruments = []
    for iid, kind, style, currency, basis in [
        ('TEST-PASSIVE', 'etf', 'passive', 'USD', 'split_adjusted_price'),
        ('TEST-ACTIVE', 'etf', 'active', 'USD', 'split_adjusted_price'),
        ('3037.TW', 'stock', 'none', 'TWD', 'split_adjusted_price'),
        ('TEST-USD-TWD', 'fx', 'none', 'TWD', 'split_adjusted_price'),
        ('TEST-BENCH', 'benchmark', 'none', 'USD', 'total_return_index')]:
        item = dict(instrument_id=iid, symbol=iid, name='TEST ONLY '+iid, asset_type=kind,
            exchange='TEST', quote_currency=currency, domicile=None, management_style=style,
            benchmark_id='TEST-BENCH' if kind == 'etf' else None, return_basis=basis,
            distributions_complete=True, corporate_actions_complete=True)
        if kind == 'etf':
            item.update(expense_ratio=0.002 if style == 'passive' else 0.006,
                expense_ratio_available_at='2023-01-01T00:00:00Z')
        if kind == 'fx':
            item.update(fx_base_currency='USD', fx_quote_currency='TWD')
        instruments.append(item)
    observations, fx_rates, distributions = [], [], []
    values = {'TEST-PASSIVE': 100.0, 'TEST-ACTIVE': 100.0, '3037.TW': 100.0, 'TEST-BENCH': 100.0}
    for n, period in enumerate(grid):
        rate = 30 + 0.8 * math.sin(n / 5)
        fx_rates.append(dict(period=period, base_currency='USD', quote_currency='TWD', rate=rate, **provenance(period)))
        for iid in values:
            if n:
                change = 0.007 + 0.025 * math.sin(n * 1.7)
                if iid == 'TEST-ACTIVE':
                    change += 0.004 * math.cos(n / 2)
                if iid == '3037.TW':
                    change += 0.02 * math.cos(n / 3)
                values[iid] *= 1 + change
            observations.append(dict(instrument_id=iid, period=period, value=values[iid], **provenance(period)))
        observations.append(dict(instrument_id='TEST-USD-TWD', period=period, value=rate, **provenance(period)))
        if n > 0 and n % 3 == 0:
            for iid in ('TEST-PASSIVE', 'TEST-ACTIVE'):
                distributions.append(dict(instrument_id=iid, ex_date=period, pay_date=period,
                    amount_per_unit=0.6 if iid == 'TEST-PASSIVE' else 0.8 + 0.1 * math.sin(n),
                    currency='USD', distribution_type='income', **provenance(period)))
    return dict(contract='MultiAssetResearchV1', schema_version='1.0.0', as_of='2026-01-01T00:00:00Z',
        base_currency='USD', objective='accumulation', periods_per_year=12, period_grid=grid,
        risk_free_rate=0.02, rolling_windows=[3, 12], instruments=instruments,
        observations=observations, distributions=distributions, fx_rates=fx_rates, regimes=[],
        cash_flow_assumptions=dict(initial_capital=100000, withholding_tax_rate=0.15,
            distribution_fee_rate=0.001, fx_fee_rate=0.001, buy_fee_rate=0.001, reinvest_fee_rate=0.001),
        holdings=[dict(instrument_id='TEST-PASSIVE', period=grid[-1], **provenance(grid[-1]),
            positions=[dict(security_id='3037.TW', weight=0.4, sector='Semiconductors', currency='TWD', factors={'value': 0.3}),
                dict(security_id='TEST-OTHER', weight=0.35, sector='Technology', currency='USD', factors={'growth': 0.5})])],
        evidence=[], adapter_lineage={'notice': 'SYNTHETIC TEST ONLY; not historical market performance'})
