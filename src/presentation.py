"""Plain-language views derived only from saved decision evidence."""
ACTION_GUIDANCE = {
    'REUSE': 'Use an existing asset after the owner confirms it fits the business need.',
    'FIX': 'Repair or extend existing content before creating another dashboard.',
    'CONSOLIDATE': 'Combine overlapping content after checking ownership and dependencies.',
    'RETIRE': 'Consider retirement only after replacement and business-impact checks.',
    'BUILD NEW': 'Propose new content because the searched assets do not cover the requested KPIs.',
    'HUMAN REVIEW': 'Clarify the missing or contradictory evidence before choosing an action.',
}


def requirements_rows(request):
    return [
        {'Requirement': 'Product', 'Value': request.get('product') or 'Needs clarification'},
        {'Requirement': 'Market / region', 'Value': request.get('market') or 'Needs clarification'},
        {'Requirement': 'Required KPIs', 'Value': ', '.join(request.get('kpis', [])) or 'Needs clarification'},
        {'Requirement': 'Business purpose', 'Value': request.get('purpose') or 'Not specified'},
        {'Requirement': 'Platform', 'Value': request.get('platform') or 'Any'},
        {'Requirement': 'Semantic model', 'Value': request.get('model_id') or 'Any'},
    ]


def candidate_rows(result):
    requested = set(result['request']['kpis'])
    rows = []
    for c in result.get('candidates', []):
        g = c['governance']
        owner = g['evidence'].get('owner') or {}
        rows.append({
            'Asset': c['asset']['asset_id'], 'Name': c['asset']['asset_name'],
            'Score / 100': c['score'], 'Covers': ', '.join(c['matched_kpis']) or 'None',
            'Missing KPIs': ', '.join(sorted(requested - set(c['matched_kpis']))) or 'None',
            'Owner': owner.get('owner_name') or 'Missing owner',
            'Review needed': '; '.join(g['missing'] + g['risks']) or 'No blocking findings',
        })
    return rows


def decision_summary(result):
    selected = [c for c in result.get('candidates', []) if c['asset']['asset_id'] in result['asset_ids']]
    owners = sorted({c['governance']['evidence']['owner']['owner_name'] for c in selected
                     if c['governance']['evidence'].get('owner')})
    unanswered = list(result['request'].get('missing', [])) + list(result['request'].get('unresolved_conflicts', []))
    unanswered += [m for c in selected for m in c['governance']['missing']]
    if result['action'] == 'HUMAN REVIEW':
        unanswered += result['reasons']
    next_step = {
        'REUSE': 'Ask the asset owner to confirm suitability, then record the review.',
        'FIX': 'Agree the missing KPIs and remediation work with the owner, then review the proposal.',
        'CONSOLIDATE': 'Agree the retained asset and remediation plan; verify dependencies and business impact.',
        'RETIRE': 'Verify the replacement, dependency completeness and business impact with the owner.',
        'BUILD NEW': 'Assign an accountable owner and validate the proposed sources and KPI definitions before building.',
        'HUMAN REVIEW': 'Correct the request or source evidence, then generate a new recommendation.',
    }[result['action']]
    return dict(meaning=ACTION_GUIDANCE[result['action']], owner=', '.join(owners) or 'Assign or confirm an accountable owner',
                unanswered=list(dict.fromkeys(unanswered)), next_step=next_step)


def score_rows(candidate, config):
    total = sum(config['weights'].values())
    return [{'Component': key, 'Value (0–1)': value, 'Weight': config['weights'][key],
             'Points / 100': round(100 * value * config['weights'][key] / total, 2)}
            for key, value in candidate['components'].items()]
