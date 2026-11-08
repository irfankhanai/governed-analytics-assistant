"""Reproducible workflow on unmodified workbook plus a clearly marked controlled reuse scenario."""
import sys
from pathlib import Path
from copy import deepcopy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_loader import load_data, load_config, ROOT
from src.request_parser import parse_request
from src.recommendation_engine import generate_recommendation
from src.database import save_decision, get_decision
from src.approvals import review_decision
from src.explanations import decision_report


def main():
    data, config = load_data(), load_config()
    output = ROOT / 'runtime' / 'demo'
    output.mkdir(parents=True, exist_ok=True)
    db = output / 'demo.sqlite3'
    first = data['Business_Requests'][0]
    cases = [
        ('source_conflict', data, parse_request(data, first['request_text'], first['product_context'], first['market_context'], request_id=first['request_id']), 'HUMAN REVIEW'),
        ('source_build', data, parse_request(data, 'Kerendia Commercial Reach Index Global', 'Kerendia', 'Global', ['Commercial Reach Index']), 'BUILD NEW'),
    ]
    scenario = deepcopy(data)
    # Explicit demo-only correction of the known asset/model scope mismatch; no source file is written.
    a = next(a for a in scenario['Analytics_Assets'] if a['asset_id'] == 'AST-0101')
    model = next(m for m in scenario['Semantic_Models'] if m['model_id'] == a['model_id'])
    model['product_scope'], model['region_scope'] = 'Beyonttra', 'EMEA'
    scenario['_meta']['scenario'] = 'Controlled reuse demonstration: SM-001 product changed to Beyonttra and region to EMEA in memory. Source SHA identifies the unchanged input workbook.'
    cases.append(('controlled_reuse', scenario, parse_request(scenario, 'Beyonttra On-Time In-Full Finland', 'Beyonttra', 'FI', ['On-Time In-Full']), 'REUSE'))
    for name, estate, request, expected in cases:
        result = generate_recommendation(estate, request, config)
        assert result['action'] == expected, (name, result['action'], result['reasons'])
        decision_id = save_decision(db, result)
        status = 'changes_requested' if expected == 'HUMAN REVIEW' else 'approved'
        review_decision(db, decision_id, status, 'Hackathon demo reviewer',
                        'Demonstration only. Review scope and required enterprise approvals before execution.', {'owner_review': True})
        record = get_decision(db, decision_id)
        assert record['status'] == status
        (output / f'{name}.md').write_text(decision_report(record), encoding='utf-8')
        print(f'{name}: {result["action"]} -> {status} -> {name}.md')
    print(f'Reports and separate demonstration database: {output}')


if __name__ == '__main__':
    main()
