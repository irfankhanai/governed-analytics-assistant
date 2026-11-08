from copy import deepcopy
import json
import pytest
from src.data_loader import load_data
from src.data_validation import validate_data
from src.request_parser import parse_request
from src.asset_matching import match_assets, detect_duplicates, scope_matches
from src.governance_engine import check_governance, evaluate_retirement_risk
from src.scoring import calculate_match_score
from src.recommendation_engine import generate_recommendation
from src.database import save_decision, get_decision, list_decisions
from src.approvals import review_decision
from src.explanations import decision_report


def request(d, kpis=None):
    return parse_request(d, 'Beyonttra in Finland', 'Beyonttra', 'FI', kpis or ['On-Time In-Full'])


def test_excel_loading_and_provenance(source):
    assert len(source['Analytics_Assets']) == 360
    assert source['Analytics_Assets'][0]['_row'] == 2
    assert len(source['_meta']['sha256']) == 64
    assert source['Governance_Rules'][0]['rule_id'] == 'RULE-001'


def test_missing_workbook(tmp_path):
    with pytest.raises(ValueError): load_data(tmp_path / 'missing.xlsx')


def test_source_validation(source):
    findings = validate_data(source)
    assert len(findings) == 21
    assert all(f['field'] == 'owner_id' and f['severity'] == 'warning' for f in findings)


def test_duplicate_key_blocks(estate, config):
    estate['Analytics_Assets'].append(deepcopy(estate['Analytics_Assets'][0]))
    assert generate_recommendation(estate, request(estate), config)['action'] == 'HUMAN REVIEW'


def test_bad_join_and_lineage(estate):
    estate['Lineage_Edges'].append(dict(source_id='UNKNOWN', target_id='UNKNOWN'))
    assert any(i['severity'] == 'error' for i in validate_data(estate))


def test_entity_and_kpi_matching(source):
    q = parse_request(source, 'Nubeqa sales growth and forecast variance in Germany')
    assert q['product'] == 'Nubeqa' and q['market'] == 'DE'
    assert set(q['kpis']) == {'Net Sales Growth', 'Forecast Variance'}
    assert not q['missing'] and not q['conflicts']


def test_real_conflict(source, config):
    r = source['Business_Requests'][0]
    q = parse_request(source, r['request_text'], r['product_context'], r['market_context'])
    assert len(q['conflicts']) == 2
    assert generate_recommendation(source, q, config)['action'] == 'HUMAN REVIEW'


def test_explicit_clarification_is_auditable(source):
    q = parse_request(source, 'Nubeqa sales in Germany', 'Beyonttra', 'DE', clarification='Requester confirms Beyonttra instead of Nubeqa.')
    assert q['conflicts'] and not q['unresolved_conflicts'] and q['clarification']


@pytest.mark.parametrize('text', ['', 'A report please', 'Nubeqa or Kerendia sales in Germany'])
def test_missing_and_ambiguous(source, config, text):
    assert generate_recommendation(source, parse_request(source, text), config)['action'] == 'HUMAN REVIEW'


def test_scope_direction(source):
    assert not scope_matches(source, dict(product_scope='Nubeqa', market_scope='DE'), dict(product='Nubeqa', market='EMEA'))[1]
    assert scope_matches(source, dict(product_scope='All Pharma', market_scope='Global'), dict(product='Nubeqa', market='DE')) == (True, True)


def test_score_formula():
    assert calculate_match_score(dict(a=1, b=0.5), dict(a=20, b=80)) == 60
    with pytest.raises(ValueError): calculate_match_score(dict(a=2), dict(a=1))


def test_controlled_reuse_and_explanation(estate, config, tmp_path):
    result = generate_recommendation(estate, request(estate), config)
    assert result['action'] == 'REUSE'
    selected = next(c for c in result['candidates'] if c['asset']['asset_id'] in result['asset_ids'])
    assert selected['coverage'] == 1
    assert not selected['governance']['risks'] and not selected['governance']['missing']
    db = tmp_path / 'audit.sqlite3'
    did = save_decision(db, result)
    review_decision(db, did, 'approved', 'Test reviewer', 'Owner confirmed intended scope.', {'owner_review': True})
    record = get_decision(db, did)
    assert record['status'] == 'approved'
    assert record['snapshot'] == result
    assert len(list_decisions(db)) == 1
    report = decision_report(record)
    assert result['asset_ids'][0] in report and estate['_meta']['sha256'] in report and 'DEMO: Test reviewer' in report


def test_real_model_contradiction(source, config):
    result = generate_recommendation(source, request(source), config)
    assert result['action'] == 'HUMAN REVIEW'
    c = next(c for c in result['candidates'] if c['asset']['asset_id'] == 'AST-0101')
    assert any('Contradictory scope' in m for m in c['governance']['missing'])


def test_real_build_new(source, config):
    q = parse_request(source, 'Commercial Reach Index for Kerendia globally', 'Kerendia', 'Global', ['Commercial Reach Index'])
    result = generate_recommendation(source, q, config)
    assert result['action'] == 'BUILD NEW'
    assert all(c['coverage'] == 0 for c in result['candidates'])


def test_rule_coverage(estate, config):
    g = check_governance(estate, estate['Analytics_Assets'][0], config)
    assert {c['rule_id'] for c in g['checks']} == {r['rule_id'] for r in estate['Governance_Rules']}
    assert all(c['source_rule'] for c in g['checks'])


def test_noncanonical_kpi_requires_fix(estate, config):
    ids = {r['kpi_id'] for r in estate['Asset_KPI_Map']}
    for k in estate['KPI_Catalog']:
        if k['kpi_id'] in ids: k['approval_status'] = 'unapproved'
    r = generate_recommendation(estate, request(estate), config)
    assert r['action'] == 'FIX'
    assert any(c['rule_id'] == 'RULE-002' and c['status'] == 'fail' for c in r['candidates'][0]['governance']['checks'])


def test_missing_owner_is_not_invalidity(estate, config):
    for a in estate['Analytics_Assets']: a['owner_id'] = None
    assert generate_recommendation(estate, request(estate), config)['action'] == 'HUMAN REVIEW'


def test_retirement_low_usage_alone_not_enough(estate, config):
    a = estate['Analytics_Assets'][0]
    for u in estate['Asset_Usage']: u['unique_users'] = 0
    g = check_governance(estate, a, config)
    r = evaluate_retirement_risk(estate, dict(asset=a, governance=g), detect_duplicates(estate, config), config)
    assert r['action'] == 'HUMAN REVIEW'
    assert not r['checks']['lifecycle_candidate']


def test_retirement_requires_replacement_and_no_downstream(estate, config):
    a = estate['Analytics_Assets'][0]
    a['lifecycle_status'] = 'candidate_retire'
    a['estimated_audience'] = 10
    for u in estate['Asset_Usage']:
        if u['asset_id'] == a['asset_id']: u['unique_users'] = 0
    g = check_governance(estate, a, config)
    pairs = detect_duplicates(estate, config)
    r = evaluate_retirement_risk(estate, dict(asset=a, governance=g), pairs, config)
    assert r['action'] == 'RETIRE'
    estate['Lineage_Edges'].append(dict(source_id=a['asset_id'], target_id='TEST-SECOND'))
    assert evaluate_retirement_risk(estate, dict(asset=a, governance=g), pairs, config)['action'] == 'HUMAN REVIEW'


def test_duplicate_detection(estate, config):
    pairs = detect_duplicates(estate, config)
    assert len(pairs) == 1 and pairs[0]['jaccard'] == 1
    estate['Analytics_Assets'][1]['market_scope'] = 'DE'
    assert not detect_duplicates(estate, config)


def test_build_new_after_search(estate, config):
    r = generate_recommendation(estate, request(estate, ['Forecast Variance']), config)
    assert r['action'] == 'BUILD NEW'
    assert r['candidates'] and all(c['coverage'] == 0 for c in r['candidates'])
    assert 'draft_specification' in r


def test_partial_existing_prefers_fix(estate, config):
    r = generate_recommendation(estate, request(estate, ['On-Time In-Full', 'Forecast Variance']), config)
    assert r['action'] == 'FIX'


def test_consolidation_union(estate, config):
    approved = {r['canonical_metric']: r['kpi_id'] for r in estate['KPI_Catalog'] if r['definition_status'] == 'canonical' and r['approval_status'] == 'approved'}
    estate['Asset_KPI_Map'] = [dict(asset_id=a['asset_id'], kpi_id=approved[m]) for a, metrics in zip(estate['Analytics_Assets'], [['On-Time In-Full', 'Net Sales'], ['On-Time In-Full', 'Forecast Variance']]) for m in metrics]
    r = generate_recommendation(estate, request(estate, ['On-Time In-Full', 'Net Sales', 'Forecast Variance']), config)
    assert r['action'] == 'CONSOLIDATE' and len(r['asset_ids']) == 2


def test_consistency_and_no_mutation(estate, config):
    original = deepcopy(estate)
    q = request(estate)
    assert generate_recommendation(estate, q, config) == generate_recommendation(estate, q, config)
    assert estate == original


def test_unknown_kpi_and_platform(source, config):
    q = parse_request(source, 'Nubeqa in Germany', 'Nubeqa', 'DE', ['Made up'], platform='Unknown')
    assert generate_recommendation(source, q, config)['action'] == 'HUMAN REVIEW'


def test_review_safeguards(estate, config, tmp_path):
    db = tmp_path / 'decisions.sqlite3'
    r = generate_recommendation(estate, request(estate), config)
    did = save_decision(db, r)
    with pytest.raises(ValueError): review_decision(db, did, 'approved', 'Reviewer', 'OK')
    review_decision(db, did, 'changes_requested', 'Reviewer', 'Clarify audience')
    with pytest.raises(ValueError): review_decision(db, did, 'rejected', 'Reviewer', 'Second review')
    assert len(get_decision(db, did)['reviews']) == 1


def test_human_review_cannot_be_approved(estate, config, tmp_path):
    db = tmp_path / 'decisions.sqlite3'
    r = generate_recommendation(estate, parse_request(estate, ''), config)
    did = save_decision(db, r)
    with pytest.raises(ValueError): review_decision(db, did, 'approved', 'Reviewer', 'OK', {'owner_review': True})


def test_retire_approval_requires_impact_and_dependencies(estate, config, tmp_path):
    db = tmp_path / 'decisions.sqlite3'
    r = generate_recommendation(estate, request(estate), config)
    r['action'], r['scope'] = 'RETIRE', 'portfolio'
    did = save_decision(db, r)
    with pytest.raises(ValueError): review_decision(db, did, 'approved', 'Reviewer', 'OK', {'owner_review': True})
    review_decision(db, did, 'approved', 'Reviewer', 'Replacement validated', dict(owner_review=True, dependency_check=True, business_impact=True))
    assert get_decision(db, did)['status'] == 'approved'
