"""Optional offline PBIP draft export. Never changes decisions or existing BI assets."""
import base64
import csv
import hashlib
import io
import json
import math
from functools import lru_cache
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from jsonschema import Draft7Validator
from referencing import Registry, Resource
from .data_loader import ROOT
from .explanations import decision_report

BASE = 'https://developer.microsoft.com/json-schemas/fabric/'
SHEET = 'Product_Market_Monthly'
# Direct source values only: no guessed DAX definitions, totals or percentage aggregation.
KPI_FIELDS = {
    'Net Sales': ('net_sales_m_eur_syn', 'Net Sales (million EUR, synthetic)'),
    'Units Shipped': ('units_shipped_syn', 'Units Shipped (synthetic)'),
    'Forecast Variance': ('forecast_variance_pct', 'Forecast Variance (%)'),
    'Market Access Coverage': ('market_access_coverage_pct_syn', 'Market Access Coverage (%)'),
    'On-Time In-Full': ('otif_pct_syn', 'On-Time In-Full (%)'),
    'Inventory Coverage': ('inventory_weeks_syn', 'Inventory Coverage (weeks)'),
}


def prepare_export(record, data):
    """Fail closed: a proposal's approval is not proof of arbitrary KPI feasibility."""
    r = record['snapshot']
    errors = []
    if record['status'] != 'approved' or not any(x.get('status') == 'approved' for x in record.get('reviews', [])):
        errors.append('Approve the proposal before exporting.')
    if r['scope'] != 'request' or r['action'] not in ['BUILD NEW', 'FIX']:
        errors.append('Export is available only for approved BUILD NEW or FIX requests. Reuse and retirement do not create new reports.')
    if r['source']['sha256'] != data['_meta']['sha256'] or r['source'].get('scenario') or data['_meta'].get('scenario'):
        errors.append('Source data differs from the reviewed workbook or is a controlled test scenario. Review a new decision first.')
    q = r['request']
    if q.get('platform') not in [None, 'Power BI'] or q.get('model_id'):
        errors.append('This standalone Power BI draft cannot satisfy another platform or a required existing semantic model.')
    if q.get('missing') or q.get('unresolved_conflicts'):
        errors.append('Resolve outstanding request questions before exporting.')
    unknown = sorted(set(q['kpis']) - set(KPI_FIELDS))
    if unknown: errors.append('No verified source mapping for: ' + ', '.join(unknown) + '. No substitute KPI will be invented.')
    if not q['kpis']: errors.append('At least one supported KPI is required.')
    products = {p['product_id']: p['product_name'] for p in data['Products']}
    markets = {m['market_id']: m for m in data['Markets']}
    if q['product'] not in set(products.values()) | {'All Pharma'}:
        errors.append('Unknown product scope.')
    if q['market'] not in set(markets) | {m['region'] for m in markets.values()} | {'Global'}:
        errors.append('Unknown market scope.')
    if errors: return {'errors': errors, 'rows': [], 'mappings': []}
    mappings = [dict(kpi=k, source_sheet=SHEET, source_field=KPI_FIELDS[k][0], output_column=KPI_FIELDS[k][1],
                     calculation='Original row value; no aggregation or new KPI calculation.') for k in q['kpis']]
    rows = []
    seen = set()
    for row in data[SHEET]:
        if row.get('product_id') not in products or row.get('market_id') not in markets:
            errors.append('Unresolved product/market reference in the source facts.')
            continue
        product, market = products[row['product_id']], markets[row['market_id']]
        if q['product'] not in ['All Pharma', product]: continue
        if q['market'] not in ['Global', row['market_id'], market['region']]: continue
        key = (row['product_id'], row['market_id'], row.get('month'))
        if key in seen: errors.append('Duplicate product-market-month row in the requested scope.')
        seen.add(key)
        if row.get('synthetic_record') is not True:
            errors.append('This exporter accepts only explicitly synthetic source records.')
        if not row.get('month') or not row.get('value_type') or not row.get('_row'):
            errors.append('Source month, value type or row provenance is missing.')
        item = {'Product': product, 'Market': row['market_id'], 'Month': str(row.get('month', ''))[:7],
                'Value type': row.get('value_type'), 'Excel row': row.get('_row')}
        for mapping in mappings:
            value = row.get(mapping['source_field'])
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                errors.append('Missing or invalid source value: ' + mapping['source_field'])
            item[mapping['output_column']] = value
        rows.append(item)
    if not rows: errors.append('No source rows match the approved product and market.')
    return dict(errors=list(dict.fromkeys(errors)), rows=rows, mappings=mappings)


def schema(path):
    return BASE + path + '/schema.json'


def table_model(name, rows):
    types = {key: 'double' if isinstance(value, (int, float)) else 'string' for key, value in rows[0].items()}
    payload = base64.b64encode(json.dumps(rows, ensure_ascii=False, allow_nan=False).encode()).decode()
    transforms = ', '.join('{' + json.dumps(key) + ', type ' + ('number' if kind == 'double' else 'text') + '}' for key, kind in types.items())
    expression = ['let', f'    Source = Table.FromRecords(Json.Document(Binary.FromText("{payload}", BinaryEncoding.Base64))),',
                  '    Typed = Table.TransformColumnTypes(Source, {' + transforms + '}, "en-US")', 'in', '    Typed']
    return dict(name=name, columns=[dict(name=k, dataType=t, sourceColumn=k, summarizeBy='none') for k, t in types.items()],
                partitions=[dict(name=name, mode='import', source=dict(type='m', expression=expression))])


def visual(table, columns, name):
    return {'$schema': schema('item/report/definition/visualContainer/1.0.0'), 'name': name,
            'position': dict(x=20, y=20, z=0, height=680, width=1240, tabOrder=0),
            'visual': {'visualType': 'tableEx', 'query': {'queryState': {'Values': {'projections': [
                {'field': {'Column': {'Expression': {'SourceRef': {'Entity': table}}, 'Property': col}},
                 'queryRef': table + '.' + col, 'nativeQueryRef': col} for col in columns]}}}}}


@lru_cache(maxsize=1)
def schema_registry():
    registry = Registry()
    documents = {}
    for path in (ROOT / 'config' / 'pbip_schemas').rglob('schema.json'):
        obj = json.loads(path.read_text(encoding='utf-8'))
        url = BASE + path.relative_to(ROOT / 'config' / 'pbip_schemas').as_posix()
        documents[url] = obj
        registry = registry.with_resource(url, Resource.from_contents(obj))
    return registry, documents


def validate_project(files):
    """Offline public-schema validation plus model/visual reference checks, not Desktop execution."""
    registry, schemas = schema_registry()
    for name, content in files.items():
        if isinstance(content, dict) and '$schema' in content:
            url = content['$schema']
            if url not in schemas: raise ValueError('Unknown schema for ' + name)
            Draft7Validator(schemas[url], registry=registry).validate(content)
    model = files['Governed.SemanticModel/model.bim']
    columns = {t['name']: {c['name'] for c in t['columns']} for t in model['model']['tables']}
    for name, content in files.items():
        if name.endswith('/visual.json'):
            for projection in content['visual']['query']['queryState']['Values']['projections']:
                col = projection['field']['Column']
                if col['Property'] not in columns.get(col['Expression']['SourceRef']['Entity'], set()):
                    raise ValueError('Visual refers to a missing model column.')
    if files['Governed.pbip']['artifacts'][0]['report']['path'] != 'Governed.Report':
        raise ValueError('Invalid report reference.')
    if files['Governed.Report/definition.pbir']['datasetReference']['byPath']['path'] != '../Governed.SemanticModel':
        raise ValueError('Invalid semantic model reference.')


def build_project(record, data):
    prepared = prepare_export(record, data)
    if prepared['errors']: raise ValueError(' '.join(prepared['errors']))
    r = record['snapshot']
    review_rows = [{'Field': k, 'Value': str(v)} for k, v in {
        'Data': 'SYNTHETIC DEMONSTRATION ONLY - not Bayer performance',
        'Decision': record['id'], 'Action': r['action'], 'Approval': record['status'],
        'Request': r['request']['text'], 'Original source SHA-256': data['_meta']['sha256'],
        'Validation': 'JSON schemas and references checked. Not opened/rendered in Power BI Desktop.',
        'Scope': 'All available monthly rows in the selected product/market scope. Text time filters are not interpreted. No aggregation; value types remain labeled.',
        'FIX proposal': 'Draft for the existing asset owner; does not alter or replace the existing report.',
    }.items()]
    files = {
        'Governed.pbip': {'$schema': schema('pbip/pbipProperties/1.0.0'), 'version': '1.0',
                          'artifacts': [{'report': {'path': 'Governed.Report'}}], 'settings': {'enableAutoRecovery': True}},
        'Governed.Report/definition.pbir': {'$schema': schema('item/report/definitionProperties/2.0.0'),
            'version': '4.0', 'datasetReference': {'byPath': {'path': '../Governed.SemanticModel'}}},
        'Governed.SemanticModel/definition.pbism': {'$schema': schema('item/semanticModel/definitionProperties/1.0.0'), 'version': '1.0'},
        'Governed.SemanticModel/model.bim': {'name': 'GovernedSynthetic', 'compatibilityLevel': 1567,
            'model': {'culture': 'en-US', 'defaultPowerBIDataSourceVersion': 'powerBI_V3',
                      'tables': [table_model('Analytics', prepared['rows']), table_model('Decision', review_rows)]}},
        'Governed.Report/definition/version.json': {'$schema': schema('item/report/definition/versionMetadata/1.0.0'), 'version': '4.0.0'},
        'Governed.Report/definition/report.json': {'$schema': schema('item/report/definition/report/1.0.0'),
                                                 'layoutOptimization': 'None', 'themeCollection': {}},
        'Governed.Report/definition/pages/pages.json': {'$schema': schema('item/report/definition/pagesMetadata/1.0.0'),
                                                        'pageOrder': ['Review', 'Data'], 'activePageName': 'Review'},
    }
    for page, title, table, rows in [('Review', 'Read first - synthetic draft', 'Decision', review_rows),
                                     ('Data', 'Synthetic monthly data', 'Analytics', prepared['rows'])]:
        folder = 'Governed.Report/definition/pages/' + page
        files[folder + '/page.json'] = {'$schema': schema('item/report/definition/page/1.0.0'), 'name': page,
                                        'displayName': title, 'displayOption': 'FitToPage', 'height': 720, 'width': 1280}
        files[folder + '/visuals/Table/visual.json'] = visual(table, list(rows[0]), 'Table')
    validate_project(files)
    files['evidence/decision.json'] = record
    files['evidence/decision.md'] = decision_report(record)
    files['evidence/export-specification.json'] = {
        'version': '1.0', 'source': data['_meta'], 'decision_id': record['id'], 'row_count': len(prepared['rows']),
        'mappings': prepared['mappings'], 'grain': 'One source product-market-month record',
        'validation': 'PBIP/PBIR public schemas and model references checked offline; Power BI Desktop not verified.',
        'limitations': ['Fixed table visuals only', 'No KPI aggregation or new measures', 'Embedded static data snapshot',
                        'No changes to existing BI assets; no publishing', 'KPI-to-field mappings are prototype mappings, not Bayer-certified measures']}
    csv_out = io.StringIO(newline='')
    writer = csv.DictWriter(csv_out, fieldnames=list(prepared['rows'][0]))
    writer.writeheader(); writer.writerows(prepared['rows'])
    files['evidence/source-rows.csv'] = csv_out.getvalue()
    files['README.txt'] = (
        'GOVERNED ANALYTICS - SYNTHETIC DRAFT POWER BI PROJECT\n\n'
        '1. Extract the entire ZIP to a short local path. Keep all folders together.\n'
        '2. Open Governed.pbip in a current Power BI Desktop version supporting PBIP/PBIR.\n'
        '3. Click Refresh to load the embedded synthetic snapshot. No workbook path or credentials are needed.\n'
        '4. Read the Review page, then inspect the Data table. Verify values against evidence/source-rows.csv.\n'
        '5. Confirm the project opens, refreshes and renders before presenting it as Desktop-tested.\n\n'
        'This package was schema/reference checked, but was not executed in Power BI Desktop.\n'
        'It is a simple two-page draft, not a production report. The data is synthetic.\n'
        'No automatic deployment, replacement or retirement occurs. For FIX, give the draft to the existing asset owner.\n'
        'Monthly percentage values are not averaged or summed. Value type distinguishes actual-like and forecast-like records.\n'
        'The embedded snapshot does not refresh from the original workbook; generate a new reviewed export for changed source data.\n')
    return files


def export_pbip(record, data):
    files = build_project(record, data)
    encoded = {name: (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) if isinstance(value, dict) else value).encode('utf-8')
               for name, value in files.items()}
    encoded['evidence/file-hashes.json'] = json.dumps({n: hashlib.sha256(v).hexdigest() for n, v in encoded.items()}, indent=2).encode()
    output = io.BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for name, value in encoded.items(): archive.writestr(name, value)
    return output.getvalue()
