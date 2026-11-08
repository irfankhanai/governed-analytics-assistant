"""Original-data export demonstration; uses a separate demo database, not live approvals."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_loader import load_data, load_config, ROOT
from src.request_parser import parse_request
from src.recommendation_engine import generate_recommendation
from src.database import save_decision, get_decision
from src.approvals import review_decision
from src.pbip_export import export_pbip


def main():
    data = load_data()
    request = parse_request(data, 'Kerendia Inventory Coverage Italy')
    result = generate_recommendation(data, request, load_config())
    assert result['action'] == 'FIX', result['action']
    output = ROOT / 'runtime' / 'pbip-demo'
    output.mkdir(parents=True, exist_ok=True)
    db = output / 'demo.sqlite3'
    decision_id = save_decision(db, result)
    review_decision(db, decision_id, 'approved', 'Export demo reviewer',
                    'Synthetic demo approval only. Draft for owner review; remediation remains outstanding.',
                    {'owner_review': True, 'remediation_plan': True})
    target = output / 'Governed-PowerBI-draft.zip'
    target.write_bytes(export_pbip(get_decision(db, decision_id), data))
    print('Original workbook -> FIX -> demo approval -> schema-checked draft:', target)
    print('Power BI Desktop opening, refresh and rendering have NOT been verified.')


if __name__ == '__main__':
    main()
