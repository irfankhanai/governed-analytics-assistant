from copy import deepcopy
import base64
import io
import json
from zipfile import ZipFile
import pytest
from src.pbip_export import prepare_export, build_project, export_pbip, validate_project
from src.request_parser import parse_request


@pytest.fixture
def approved(source):
    # Controlled approved request fixture. It does not assert this is the source engine's recommendation.
    request = parse_request(source, 'Nubeqa Net Sales Germany', 'Nubeqa', 'DE', ['Net Sales'])
    return {'id': 'TEST-PBIP', 'status': 'approved', 'reviews': [{'status': 'approved', 'reviewer': 'DEMO tester'}],
            'snapshot': {'scope': 'request', 'action': 'BUILD NEW', 'source': source['_meta'], 'request': request,
                         'asset_ids': [], 'candidates': [], 'reasons': ['Controlled export test'], 'next_steps': ['Validate in Desktop']}}


def test_archive_schemas_references_and_source_values(source, approved):
    original = deepcopy(source)
    files = build_project(approved, source)
    validate_project(files)
    prepared = prepare_export(approved, source)
    assert len(prepared['rows']) == 10
    originals = [r for r in source['Product_Market_Monthly'] if r['product_id'] == 'P-NUB' and r['market_id'] == 'DE']
    assert [r['Net Sales (million EUR, synthetic)'] for r in prepared['rows']] == [r['net_sales_m_eur_syn'] for r in originals]
    expression = files['Governed.SemanticModel/model.bim']['model']['tables'][0]['partitions'][0]['source']['expression'][1]
    payload = expression.split('Binary.FromText("')[1].split('"')[0]
    assert json.loads(base64.b64decode(payload)) == prepared['rows']
    with ZipFile(io.BytesIO(export_pbip(approved, source))) as archive:
        assert 'Governed.pbip' in archive.namelist()
        assert 'evidence/source-rows.csv' in archive.namelist()
        assert json.loads(archive.read('evidence/export-specification.json'))['row_count'] == 10
        assert all('..' not in p and not p.startswith('/') for p in archive.namelist())
    assert source == original


@pytest.mark.parametrize('status', ['pending', 'rejected', 'changes_requested'])
def test_approval_required(source, approved, status):
    approved['status'] = status
    with pytest.raises(ValueError, match='Approve'): export_pbip(approved, source)


@pytest.mark.parametrize('action', ['REUSE', 'CONSOLIDATE', 'RETIRE', 'HUMAN REVIEW'])
def test_no_duplicate_report_for_other_actions(source, approved, action):
    approved['snapshot']['action'] = action
    with pytest.raises(ValueError, match='only'): export_pbip(approved, source)


def test_unsupported_kpi_not_fabricated(source, approved):
    approved['snapshot']['request']['kpis'].append('Commercial Reach Index')
    with pytest.raises(ValueError, match='No verified source mapping'): export_pbip(approved, source)


def test_stale_source_blocks(source, approved):
    approved['snapshot']['source'] = {'sha256': 'old'}
    with pytest.raises(ValueError, match='differs'): export_pbip(approved, source)


def test_missing_source_value_blocks(source, approved):
    changed = deepcopy(source)
    changed['Product_Market_Monthly'][0]['net_sales_m_eur_syn'] = None
    with pytest.raises(ValueError, match='Missing or invalid'): export_pbip(approved, changed)


def test_region_filter_and_rate_values(source, approved):
    approved['snapshot']['request'].update(market='EMEA', kpis=['Forecast Variance'])
    result = prepare_export(approved, source)
    assert not result['errors']
    emea = {m['market_id'] for m in source['Markets'] if m['region'] == 'EMEA'}
    assert {r['Market'] for r in result['rows']} == emea
    expected = [r['forecast_variance_pct'] for r in source['Product_Market_Monthly'] if r['product_id'] == 'P-NUB' and r['market_id'] in emea]
    assert [r['Forecast Variance (%)'] for r in result['rows']] == expected


def test_broken_visual_rejected(source, approved):
    files = build_project(approved, source)
    files['Governed.Report/definition/pages/Data/visuals/Table/visual.json']['visual']['query']['queryState']['Values']['projections'][0]['field']['Column']['Property'] = 'Invented'
    with pytest.raises(ValueError, match='missing model column'): validate_project(files)


def test_incompatible_target_blocks(source, approved):
    approved['snapshot']['request']['platform'] = 'Tableau'
    with pytest.raises(ValueError, match='another platform'): export_pbip(approved, source)
