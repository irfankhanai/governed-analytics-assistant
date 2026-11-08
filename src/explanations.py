import json
from .presentation import decision_summary, candidate_rows


def decision_report(record):
    """Downloadable Markdown with complete reproducibility snapshot, no hidden live lookups."""
    r = record['snapshot']
    summary = decision_summary(r)
    lines = ['# Governed analytics decision', '', '**Synthetic demonstration data — not Bayer performance.**', '',
             f"Decision: {record['id']}", f"Request: {r['request']['request_id']}",
             f"Original request: {r['request']['text']}", f"Recommendation: **{r['action']}** ({r['scope']})",
             f"Assets: {', '.join(r['asset_ids']) or 'None selected'}", f"Approval status: **{record['status']}**", '',
             'Approval records a proposal only. It performs no BI lifecycle operation.', '', '## Reasons']
    lines += ['- ' + reason for reason in r['reasons']]
    lines += ['', '## What this means', summary['meaning'], '', 'Responsible owner: ' + summary['owner'],
              '', 'Next action: ' + summary['next_step'], '', '## Unresolved questions']
    lines += ['- ' + item for item in summary['unanswered']] or ['None identified in this decision.']
    lines += ['', '## Existing asset coverage']
    for row in candidate_rows(r):
        lines.append(f"- {row['Asset']}: covers {row['Covers']}; missing KPIs: {row['Missing KPIs']}; owner: {row['Owner']}; score: {row['Score / 100']} / 100.")
    lines += ['', '## Next steps'] + ['- ' + step for step in r['next_steps']]
    lines += ['', '## Review history', '```json', json.dumps(record['reviews'], indent=2), '```',
              '', '## Evidence and reproducibility snapshot',
              'Scores are weighted indices, not probabilities. Source records include sheet names and Excel row numbers.',
              '```json', json.dumps(r, indent=2), '```']
    return '\n'.join(lines)
