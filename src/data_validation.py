"""Validate IDs and joins without repairing or silently discarding source records."""
PRIMARY = {'Products': 'product_id', 'Markets': 'market_id', 'Owners': 'owner_id',
           'KPI_Catalog': 'kpi_id', 'Workspaces': 'workspace_id', 'Semantic_Models': 'model_id',
           'Analytics_Assets': 'asset_id', 'Business_Requests': 'request_id',
           'Governance_Rules': 'rule_id', 'Governance_Signals': 'signal_id', 'Data_Quality': 'issue_id'}
JOINS = [
    ('Analytics_Assets', 'owner_id', 'Owners', 'owner_id'),
    ('Analytics_Assets', 'workspace_id', 'Workspaces', 'workspace_id'),
    ('Analytics_Assets', 'model_id', 'Semantic_Models', 'model_id'),
    ('Semantic_Models', 'owner_id', 'Owners', 'owner_id'),
    ('Semantic_Models', 'workspace_id', 'Workspaces', 'workspace_id'),
    ('KPI_Catalog', 'owner_id', 'Owners', 'owner_id'),
    ('Asset_KPI_Map', 'asset_id', 'Analytics_Assets', 'asset_id'),
    ('Asset_KPI_Map', 'kpi_id', 'KPI_Catalog', 'kpi_id'),
    ('Asset_Usage', 'asset_id', 'Analytics_Assets', 'asset_id'),
    ('Governance_Signals', 'asset_id', 'Analytics_Assets', 'asset_id'),
    ('Migration_Backlog', 'source_asset_id', 'Analytics_Assets', 'asset_id'),
    ('Migration_Backlog', 'candidate_target_model_id', 'Semantic_Models', 'model_id'),
]
for sheet in ['Product_Market_Monthly', 'Launch_Milestones', 'Market_Access', 'Supply_Operations']:
    JOINS.extend([(sheet, 'product_id', 'Products', 'product_id'), (sheet, 'market_id', 'Markets', 'market_id')])


def validate_data(data):
    issues = []
    def add(sheet, row, field, detail, severity='warning'):
        issues.append(dict(sheet=sheet, row=row, field=field, detail=detail, severity=severity))
    required = set(PRIMARY) | {j[0] for j in JOINS} | {'Lineage_Edges', 'Data_Dictionary', 'START_HERE'}
    for sheet in sorted(required):
        if sheet not in data:
            add(sheet, None, '', 'Required sheet missing', 'error')
        elif not data[sheet] and sheet in {'Analytics_Assets', 'KPI_Catalog', 'Products', 'Markets', 'Governance_Rules'}:
            add(sheet, None, '', 'Core catalogue is empty', 'error')
    for sheet, key in PRIMARY.items():
        seen = set()
        for row in data.get(sheet, []):
            value = row.get(key)
            if not value or value in seen:
                add(sheet, row.get('_row'), key, f'Missing or duplicate primary key: {value}', 'error')
            seen.add(value)
    for sheet, field, target, key in JOINS:
        keys = {r.get(key) for r in data.get(target, [])}
        for row in data.get(sheet, []):
            if row.get(field) not in keys:
                add(sheet, row.get('_row'), field, f'Unresolved {target} reference: {row.get(field)}')
    nodes = {r['asset_id'] for r in data.get('Analytics_Assets', [])} | {r['model_id'] for r in data.get('Semantic_Models', [])}
    for row in data.get('Lineage_Edges', []):
        for field in ['source_id', 'target_id']:
            if row.get(field) not in nodes:
                add('Lineage_Edges', row.get('_row'), field, 'Unresolved lineage node', 'error')
    for sheet, keys in [('Asset_KPI_Map', ['asset_id', 'kpi_id']), ('Asset_Usage', ['asset_id', 'month'])]:
        seen = set()
        for row in data.get(sheet, []):
            key = tuple(row.get(k) for k in keys)
            if key in seen:
                add(sheet, row.get('_row'), ','.join(keys), f'Duplicate composite key: {key}', 'error')
            seen.add(key)
    return issues
