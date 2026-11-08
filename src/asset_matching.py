import re
from itertools import combinations
from .data_loader import index, related
from .governance_engine import check_governance
from .scoring import calculate_match_score


def scope_matches(data, asset, request):
    product = asset.get('product_scope') in [request.get('product'), 'All Pharma']
    market = asset.get('market_scope')
    wanted = request.get('market')
    markets = index(data, 'Markets', 'market_id')
    # A country cannot satisfy a whole-region request. Global can satisfy a country or region.
    market_match = market == 'Global' or market == wanted or (wanted in markets and market == markets[wanted]['region'])
    return product, market_match


def match_assets(data, request, config):
    results = []
    for asset in data['Analytics_Assets']:
        p, m = scope_matches(data, asset, request)
        g = check_governance(data, asset, config)
        metrics = {k['canonical_metric'] for k in g['evidence']['kpis']}
        matched = sorted(metrics & set(request['kpis']))
        coverage = len(matched) / len(request['kpis']) if request['kpis'] else 0
        platform_ok = not request.get('platform') or request['platform'] == asset['platform']
        model_ok = not request.get('model_id') or request['model_id'] == asset['model_id']
        words = set(re.findall(r'\w+', request.get('purpose', '').lower()))
        title = set(re.findall(r'\w+', asset['asset_name'].lower()))
        usage = g['mean_monthly_users']
        components = dict(product=float(p), market=float(m), kpi=coverage,
                          purpose=len(words & title)/len(words) if words else 0,
                          governance=sum(c['status'] == 'pass' for c in g['checks'])/len(g['checks']),
                          freshness=float(bool(g['evidence']['model'] and g['evidence']['model']['refresh_status'] == 'healthy' and not g['evidence']['quality'])),
                          usage=min(usage / 100, 1) if usage is not None else 0)
        if p and m:
            results.append(dict(asset=asset, governance=g, matched_kpis=matched, coverage=coverage,
                                compatible=platform_ok and model_ok, components=components,
                                score=calculate_match_score(components, config['weights']),
                                match_reasons=[f'Product scope {asset["product_scope"]}', f'Market scope {asset["market_scope"]}',
                                               f'Canonical KPI coverage {len(matched)}/{len(request["kpis"])}',
                                               f'Platform compatible: {platform_ok}', f'Model compatible: {model_ok}']))
    return sorted(results, key=lambda r: (-r['score'], r['asset']['asset_id']))


def detect_duplicates(data, config):
    catalog = index(data, 'KPI_Catalog', 'kpi_id')
    sets = {}
    for a in data['Analytics_Assets']:
        sets[a['asset_id']] = {catalog[r['kpi_id']]['canonical_metric'] for r in related(data, 'Asset_KPI_Map', 'asset_id', a['asset_id']) if r['kpi_id'] in catalog}
    pairs = []
    for a, b in combinations(data['Analytics_Assets'], 2):
        if (a['product_scope'], a['market_scope']) != (b['product_scope'], b['market_scope']): continue
        left, right = sets[a['asset_id']], sets[b['asset_id']]
        similarity = len(left & right) / len(left | right) if left | right else 0
        if similarity >= config['thresholds']['duplicate_jaccard']:
            pairs.append(dict(left=a['asset_id'], right=b['asset_id'], jaccard=similarity,
                              shared_kpis=sorted(left & right), same_model=a['model_id'] == b['model_id'],
                              interpretation='Potential overlap, not proof of equivalent business purpose.'))
    return pairs
