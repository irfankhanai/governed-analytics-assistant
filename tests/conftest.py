from copy import deepcopy
import pytest
from src.data_loader import load_data, load_config


@pytest.fixture(scope='session')
def source():
    return load_data()


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def estate(source):
    """Controlled in-memory scenario derived from supplied records; never writes workbook."""
    d = deepcopy(source)
    d['_meta']['scenario'] = 'Controlled in-memory fixture derived from source; modified scopes and records. SHA identifies original workbook only.'
    a = next(a for a in d['Analytics_Assets'] if a['asset_id'] == 'AST-0101')
    model = next(m for m in d['Semantic_Models'] if m['model_id'] == a['model_id'])
    model['product_scope'], model['region_scope'] = 'Beyonttra', 'EMEA'
    b = deepcopy(a)
    b['asset_id'] = 'TEST-SECOND'
    b['asset_name'] = 'Controlled second asset'
    d['Analytics_Assets'] = [a, b]
    ids = {a['asset_id'], b['asset_id']}
    for sheet, key in [('Asset_KPI_Map', 'asset_id'), ('Asset_Usage', 'asset_id'), ('Governance_Signals', 'asset_id'), ('Migration_Backlog', 'source_asset_id')]:
        d[sheet] = [r for r in d[sheet] if r[key] == a['asset_id']]
        copies = deepcopy(d[sheet])
        for r in copies:
            r[key] = b['asset_id']
            if 'signal_id' in r: r['signal_id'] = 'TEST-' + r['signal_id']
        d[sheet] += copies
    d['Lineage_Edges'] = [r for r in d['Lineage_Edges'] if not str(r['source_id']).startswith('AST-') and not str(r['target_id']).startswith('AST-')]
    d['Lineage_Edges'] += [dict(source_id=x['model_id'], target_id=x['asset_id'], edge_type='MODEL_TO_ASSET', relationship='test dependency') for x in [a, b]]
    d['Data_Quality'] = [r for r in d['Data_Quality'] if r['sheet'] != 'Analytics_Assets' or r['record_id'] in ids]
    return d
