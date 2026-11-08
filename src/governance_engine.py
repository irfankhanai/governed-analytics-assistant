"""Dataset rules are policy; checks below are explicitly documented operationalizations."""
from .data_loader import index, related


def check_governance(data, asset, config):
    aid = asset['asset_id']
    model = index(data, 'Semantic_Models', 'model_id').get(asset.get('model_id'))
    owner = index(data, 'Owners', 'owner_id').get(asset.get('owner_id'))
    mapping = related(data, 'Asset_KPI_Map', 'asset_id', aid)
    catalog = index(data, 'KPI_Catalog', 'kpi_id')
    kpis = [catalog[r['kpi_id']] for r in mapping if r['kpi_id'] in catalog]
    usage = sorted(related(data, 'Asset_Usage', 'asset_id', aid), key=lambda r: str(r.get('month') or ''))
    latest_month = max((str(r.get('month') or '') for r in data['Asset_Usage']), default='')
    recent = usage[-config['thresholds']['usage_months']:]
    lineage = [r for r in data['Lineage_Edges'] if aid in [r['source_id'], r['target_id']] or (model and model['model_id'] in [r['source_id'], r['target_id']])]
    signals = related(data, 'Governance_Signals', 'asset_id', aid)
    dq = [r for r in data['Data_Quality'] if (r['sheet'] == 'Analytics_Assets' and r['record_id'] == aid) or (model and r['sheet'] == 'Semantic_Models' and r['record_id'] == model['model_id']) or (r['sheet'] == 'KPI_Catalog' and r['record_id'] in {k['kpi_id'] for k in kpis})]
    migration = related(data, 'Migration_Backlog', 'source_asset_id', aid)
    workspace = index(data, 'Workspaces', 'workspace_id').get(asset.get('workspace_id'))
    checks = []
    def check(rule, status, reason):
        source = index(data, 'Governance_Rules', 'rule_id').get(rule)
        checks.append(dict(rule_id=rule, status=status if source else 'unknown', explanation=reason,
                           source_rule=source, implementation='config/rules.yaml + src/governance_engine.py'))
    trusted = asset.get('endorsement') in ['certified', 'promoted']
    check('RULE-001', 'pass' if trusted else 'warning', f"Endorsement: {asset.get('endorsement')}; every asset is searched before BUILD NEW.")
    bad_kpis = [k['kpi_id'] for k in kpis if k.get('approval_status') != 'approved' or k.get('definition_status') != 'canonical']
    check('RULE-002', 'unknown' if not mapping or len(kpis) != len(mapping) else 'fail' if bad_kpis else 'pass', f'Noncanonical/unapproved KPI IDs: {bad_kpis}; mapped KPI count: {len(mapping)}.')
    check('RULE-003', 'unknown' if not owner else 'pass' if owner.get('status') == 'active' else 'fail', f"Asset owner: {asset.get('owner_id')}; status: {owner.get('status') if owner else 'missing'}.")
    linked = any(r['source_id'] == asset.get('model_id') and r['target_id'] == aid for r in lineage)
    check('RULE-004', 'pass' if linked else 'unknown', f'Upstream model edge present: {linked}. Recorded dependencies are shown; completeness is not certified.')
    reach = asset.get('estimated_audience')
    check('RULE-005', 'unknown' if reach is None else 'fail' if reach >= config['thresholds']['high_audience'] and not trusted else 'pass', f'Estimated audience: {reach}; endorsement: {asset.get("endorsement")}.')
    check('RULE-006', 'warning' if asset.get('platform') == 'Tableau' else 'pass', f"Platform: {asset.get('platform')}; migration entries: {len(migration)}. Candidate paths are not approvals.")
    check('RULE-007', 'unknown' if not model else 'pass' if model.get('ai_readiness') == 'good' and model.get('ai_issue_pattern') == 'clear' else 'fail', f"Model AI readiness: {model.get('ai_readiness') if model else 'missing'}; issue: {model.get('ai_issue_pattern') if model else 'missing'}.")
    check('RULE-008', 'pass', 'Source asset, KPI, usage, model, quality, signal and lineage records are attached with sheet/row provenance.')
    missing = [c['explanation'] for c in checks if c['status'] == 'unknown']
    if not recent or len(recent) < config['thresholds']['usage_months'] or str(recent[-1].get('month') or '') != latest_month:
        missing.append('Usage evidence is incomplete relative to the workbook latest month.')
    if not workspace: missing.append('Workspace reference is unresolved.')
    if not model or model.get('refresh_status') not in ['healthy', 'warning', 'failed']:
        missing.append('Semantic model refresh evidence is missing or unknown.')
    risks = [c['explanation'] for c in checks if c['status'] == 'fail']
    if model and model.get('refresh_status') != 'healthy': risks.append(f"Model refresh: {model.get('refresh_status')}")
    if model:
        market_row = index(data, 'Markets', 'market_id').get(asset.get('market_scope'))
        expected_region = market_row['region'] if market_row else asset.get('market_scope')
        if model.get('product_scope') not in [asset.get('product_scope'), 'All Pharma']:
            missing.append(f"Contradictory scope: asset product {asset.get('product_scope')} versus model product {model.get('product_scope')}.")
        if model.get('region_scope') not in [expected_region, 'Global']:
            missing.append(f"Contradictory scope: asset market {asset.get('market_scope')} versus model region {model.get('region_scope')}.")
        model_owner = index(data, 'Owners', 'owner_id').get(model.get('owner_id'))
        if not model_owner: missing.append('Semantic model owner is unresolved.')
        elif model_owner.get('status') != 'active': risks.append('Semantic model owner is inactive.')
    else:
        model_owner = None
    if asset.get('lifecycle_status') != 'active': risks.append(f"Lifecycle: {asset.get('lifecycle_status')}")
    risks += [f"Quality {r['issue_id']}: {r['field']}={r['issue_value']} ({r['severity']})" for r in dq]
    risks += [f"Signal {r['signal_id']}: {r['signal_code']} ({r['status']}); requires validation" for r in signals if r['severity'] == 'high']
    numeric = [r['unique_users'] for r in recent if isinstance(r.get('unique_users'), (int, float)) and r['unique_users'] >= 0]
    if len(numeric) != len(recent): missing.append('Invalid or missing monthly usage values.')
    return dict(checks=checks, risks=risks, missing=missing,
                mean_monthly_users=sum(numeric) / len(numeric) if numeric else None,
                evidence=dict(asset=asset, model=model, owner=owner, model_owner=model_owner, workspace=workspace,
                              kpi_map=mapping, kpis=kpis, usage=recent, lineage=lineage, quality=dq,
                              signals=signals, migration=migration))


def evaluate_retirement_risk(data, candidate, duplicates, config):
    """Only propose retirement; even absence of recorded edges needs human verification."""
    a, g = candidate['asset'], candidate['governance']
    outgoing = [r for r in data['Lineage_Edges'] if r['source_id'] == a['asset_id']]
    replacements = sorted({p['right'] if p['left'] == a['asset_id'] else p['left'] for p in duplicates if a['asset_id'] in [p['left'], p['right']]})
    # A replacement must cover every canonical metric, not merely meet the overlap threshold.
    valid = []
    for rid in replacements:
        other = index(data, 'Analytics_Assets', 'asset_id')[rid]
        og = check_governance(data, other, config)
        required = {k['canonical_metric'] for k in g['evidence']['kpis']}
        covered = {k['canonical_metric'] for k in og['evidence']['kpis']}
        if required and required <= covered and not og['risks'] and not og['missing'] and other['endorsement'] in ['certified', 'promoted']:
            valid.append(rid)
    checks = dict(lifecycle_candidate=a.get('lifecycle_status') == 'candidate_retire',
                  low_usage=g['mean_monthly_users'] is not None and g['mean_monthly_users'] < config['thresholds']['low_monthly_users'],
                  replacement_available=bool(valid), no_recorded_downstream=not outgoing,
                  limited_audience=a.get('estimated_audience') is not None and a['estimated_audience'] < config['thresholds']['retirement_audience_limit'],
                  evidence_complete=not g['missing'])
    return dict(action='RETIRE' if all(checks.values()) else 'HUMAN REVIEW', scope='portfolio', asset_ids=[a['asset_id']],
                checks=checks, replacements=valid, downstream=outgoing,
                next_steps=['Confirm lineage completeness and business impact with the accountable owner.',
                            'Confirm replacement suitability and obtain lifecycle approval before any retirement.'])
