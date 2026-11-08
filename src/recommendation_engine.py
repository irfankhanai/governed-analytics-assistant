from itertools import combinations
from .asset_matching import match_assets, detect_duplicates
from .data_validation import validate_data
from .governance_engine import evaluate_retirement_risk


def generate_recommendation(data, request, config):
    validation = validate_data(data)
    candidates = match_assets(data, request, config)
    compatible = [c for c in candidates if c['compatible']]
    full = [c for c in compatible if c['coverage'] >= config['thresholds']['minimum_kpi_coverage']]
    clean = [c for c in full if not c['governance']['risks'] and not c['governance']['missing']
             and c['asset']['endorsement'] in ['certified', 'promoted'] and c['score'] >= config['thresholds']['reuse_score']]
    action, selected, reasons = 'HUMAN REVIEW', [], []
    blockers = request['missing'] + request['unresolved_conflicts']
    if any(i['severity'] == 'error' for i in validation): blockers.append('Dataset integrity errors must be resolved before a decision.')
    duplicates = detect_duplicates(data, config)
    if blockers:
        reasons = blockers
    elif clean:
        action, selected = 'REUSE', [clean[0]['asset']['asset_id']]
        reasons = ['Existing endorsed asset covers every requested canonical KPI and scope, meets the score threshold and has no unresolved governance checks.']
    elif full:
        best = next((c for c in full if not c['governance']['missing']), full[0])
        selected = [best['asset']['asset_id']]
        if best['governance']['missing']:
            reasons = best['governance']['missing']
        else:
            action = 'FIX'
            reasons = best['governance']['risks'] or ['Validate endorsement and business purpose to meet reuse requirements.']
    else:
        for a, b in combinations(compatible, 2):
            shared = set(a['matched_kpis']) & set(b['matched_kpis'])
            covered = set(a['matched_kpis']) | set(b['matched_kpis'])
            if shared and covered >= set(request['kpis']) and not a['governance']['missing'] and not b['governance']['missing']:
                action, selected = 'CONSOLIDATE', [a['asset']['asset_id'], b['asset']['asset_id']]
                reasons = ['Two scope-compatible assets overlap on ' + ', '.join(sorted(shared)) + ' and together cover the requested KPIs. Owner review and remediation are required.']
                break
        if not selected:
            # Missing KPI maps can conceal suitable assets; do not use incomplete inventory as absence proof.
            incomplete = [c for c in candidates if c['governance']['missing'] and (c['coverage'] > 0 or not c['governance']['evidence']['kpi_map'])]
            partial = [c for c in compatible if c['coverage'] > 0]
            incompatible_full = [c for c in candidates if c['coverage'] == 1 and not c['compatible']]
            if incomplete:
                reasons = ['Scope-relevant assets have incomplete evidence; clarify before authorizing new content.']
            elif incompatible_full:
                selected = [incompatible_full[0]['asset']['asset_id']]
                reasons = ['Existing content covers the business need but conflicts with a requested platform/model. Review reuse or migration first.']
            elif partial:
                action, selected = 'FIX', [partial[0]['asset']['asset_id']]
                reasons = ['Extend the closest scope-compatible asset with missing KPIs before creating separate content.']
            else:
                action = 'BUILD NEW'
                reasons = ['No scope-compatible asset covers any requested KPI after the complete inventory search. A new specification needs governance approval.']
    chosen = [c for c in candidates if c['asset']['asset_id'] in selected]
    alternatives = []
    for c in candidates:
        aid = c['asset']['asset_id']
        alternatives.append(dict(asset_id=aid, selected=aid in selected, score=c['score'], coverage=c['coverage'],
                                 disposition='Selected for review' if aid in selected else 'Alternative: ' + (
                                     'platform/model constraint differs' if not c['compatible'] else
                                     'incomplete KPI coverage' if c['coverage'] < 1 else
                                     'missing evidence' if c['governance']['missing'] else
                                     'governance remediation needed' if c['governance']['risks'] else 'lower rank or endorsement/score threshold not met')))
    models = [m for m in data['Semantic_Models'] if m.get('product_scope') in [request.get('product'), 'All Pharma']]
    result = dict(request=request, action=action, scope='request', asset_ids=selected, reasons=reasons,
                  risks=sorted({r for c in chosen for r in c['governance']['risks']}), candidates=candidates,
                  alternatives=alternatives, duplicate_candidates=duplicates,
                  portfolio=[evaluate_retirement_risk(data, c, duplicates, config) for c in candidates if c['asset']['lifecycle_status'] == 'candidate_retire'],
                  model_candidates=models, source=data['_meta'], config=config, validation=validation,
                  approval_status='pending', assumptions=[
                      'All Pharma and Global assets are treated as scope supersets, subject to owner confirmation.',
                      'KPI variants match by canonical_metric; approval and definition status are checked separately.',
                      'Purpose matching uses title keywords only. Usage reflects the latest workbook period, not live telemetry.',
                      'Lineage absence does not prove absence of dependencies. No production changes are performed.'],
                  next_steps=['Resolve missing evidence and flagged risks.', 'Obtain accountable owner and governance review.',
                              'Execute any approved change manually in the enterprise BI process.'])
    if action == 'BUILD NEW':
        result['draft_specification'] = dict(product=request['product'], market=request['market'], kpis=request['kpis'],
            purpose=request['purpose'] or request['text'], semantic_models_to_assess=[m['model_id'] for m in models],
            source_sheets_to_assess=['Product_Market_Monthly', 'Market_Access', 'Supply_Operations', 'Launch_Milestones'],
            ownership='Assign active business and technical owners before build.',
            approvals=['KPI definitions', 'data access', 'semantic model fitness', 'business sponsorship'],
            note='Draft only. Source suitability is unverified. No Power BI artifact has been generated.')
    return result
