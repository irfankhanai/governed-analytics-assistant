import json
from .database import connect, utcnow


def review_decision(path, decision_id, status, reviewer, comments, attestations=None):
    if status not in ['approved', 'rejected', 'changes_requested']:
        raise ValueError('Invalid approval status.')
    if not reviewer.strip() or not comments.strip():
        raise ValueError('A demo reviewer identity and comments are required.')
    attestations = attestations or {}
    with connect(path) as db:
        row = db.execute('SELECT action, status, snapshot FROM decisions WHERE id=?', (decision_id,)).fetchone()
        if not row: raise ValueError('Unknown decision.')
        if row['status'] != 'pending': raise ValueError('This decision is already reviewed. Generate a revised decision for another review.')
        snapshot = json.loads(row['snapshot'])
        if status == 'approved':
            if row['action'] == 'HUMAN REVIEW': raise ValueError('Resolve the request and generate a new recommendation before approving.')
            if not attestations.get('owner_review'): raise ValueError('Owner review attestation is required.')
            if row['action'] in ['CONSOLIDATE', 'RETIRE'] and not all(attestations.get(k) for k in ['dependency_check', 'business_impact']):
                raise ValueError('Dependency and business impact checks are required.')
            if snapshot.get('risks') and not attestations.get('remediation_plan'):
                raise ValueError('A remediation plan must be acknowledged for flagged risks.')
        updated = db.execute('UPDATE decisions SET status=? WHERE id=? AND status=?', (status, decision_id, 'pending'))
        if updated.rowcount != 1: raise ValueError('Another reviewer already updated this decision.')
        db.execute('INSERT INTO reviews(decision_id,timestamp,reviewer,status,comments,attestations) VALUES(?,?,?,?,?,?)',
                   (decision_id, utcnow(), 'DEMO: ' + reviewer.strip(), status, comments.strip(), json.dumps(attestations)))
