import pytest
from src.presentation import decision_summary, candidate_rows, score_rows
from src.request_parser import parse_request
from src.recommendation_engine import generate_recommendation


def test_explanation_uses_saved_evidence(estate, config):
    request = parse_request(estate, 'Beyonttra in Finland', 'Beyonttra', 'FI', ['On-Time In-Full', 'Forecast Variance'])
    result = generate_recommendation(estate, request, config)
    rows = candidate_rows(result)
    assert rows[0]['Missing KPIs'] == 'Forecast Variance'
    assert rows[0]['Owner'] == result['candidates'][0]['governance']['evidence']['owner']['owner_name']
    summary = decision_summary(result)
    assert summary['owner'] != 'Assign or confirm an accountable owner'
    points = score_rows(result['candidates'][0], config)
    assert sum(r['Points / 100'] for r in points) == pytest.approx(result['candidates'][0]['score'], abs=0.04)


def test_missing_requirements_are_visible(source, config):
    result = generate_recommendation(source, parse_request(source, ''), config)
    assert 'Business request text is required.' in decision_summary(result)['unanswered']
