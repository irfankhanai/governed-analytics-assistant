"""Conservative catalogue extraction; no inference is represented as a source fact."""
import re
import uuid

ALIASES = {'sales': 'Net Sales', 'sales growth': 'Net Sales Growth', 'market access': 'Market Access Coverage',
           'forecast accuracy': 'Demand Forecast Accuracy', 'otif': 'On-Time In-Full',
           'inventory': 'Inventory Coverage'}


def contains(text, phrase):
    return bool(re.search(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', text, re.I))


def parse_request(data, text, product=None, market=None, kpis=None, purpose='', request_id=None,
                  platform=None, model_id=None, clarification=''):
    text = (text or '').strip()
    products = [r['product_name'] for r in data['Products']] + ['All Pharma']
    markets = {r['market_id']: r for r in data['Markets']}
    scopes = list(markets) + sorted({r['region'] for r in markets.values()}) + ['Global']
    found_products = [p for p in products if contains(text, p)]
    found_markets = [m for m, r in markets.items() if contains(text, r['market_name']) or re.search(r'(?<!\w)' + re.escape(m) + r'(?!\w)', text)]
    found_markets += [s for s in scopes if s not in markets and contains(text, s)]
    metrics = sorted({r['canonical_metric'] for r in data['KPI_Catalog']})
    found_metrics = [m for m in metrics if contains(text, m)]
    for alias, canonical in ALIASES.items():
        if contains(text, alias) and canonical not in found_metrics:
            if alias == 'sales' and ('Net Sales Growth' in found_metrics or contains(text, 'sales growth')):
                continue
            found_metrics.append(canonical)
    conflicts = []
    missing = []
    for label, selected, found in [('product', product, found_products), ('market', market, found_markets)]:
        if selected and any(v != selected for v in found):
            conflicts.append(f'{label}: structured selection {selected}; text mentions {", ".join(found)}')
        elif len(found) > 1:
            conflicts.append(f'Multiple {label} scopes in text: {", ".join(found)}')
    product = product or (found_products[0] if len(found_products) == 1 else None)
    market = market or (found_markets[0] if len(found_markets) == 1 else None)
    selected_kpis = list(kpis) if kpis is not None else found_metrics
    if kpis is not None and set(found_metrics) - set(kpis):
        conflicts.append('Selected KPIs omit text requirements: ' + ', '.join(sorted(set(found_metrics) - set(kpis))))
    if not text: missing.append('Business request text is required.')
    if product not in products: missing.append('Select a known product scope.')
    if market not in scopes: missing.append('Select a known market, region or Global scope.')
    if not selected_kpis: missing.append('Select at least one catalogue KPI.')
    if set(selected_kpis) - set(metrics): missing.append('Unknown KPI supplied; resolve to the catalogue.')
    if platform and platform not in {a['platform'] for a in data['Analytics_Assets']}:
        missing.append('Unknown platform.')
    if model_id and model_id not in {m['model_id'] for m in data['Semantic_Models']}:
        missing.append('Unknown semantic model.')
    return dict(request_id=request_id or 'NEW-' + uuid.uuid4().hex[:10], text=text, product=product,
                market=market, kpis=selected_kpis, purpose=purpose, platform=platform, model_id=model_id,
                extracted=dict(products=found_products, markets=found_markets, kpis=found_metrics),
                conflicts=conflicts, missing=missing, clarification=clarification,
                unresolved_conflicts=conflicts if not clarification.strip() else [])
