from streamlit.testing.v1 import AppTest
from src.data_loader import ROOT


def test_all_pages_and_request_approval(tmp_path, monkeypatch):
    monkeypatch.setenv('GOVERNED_ANALYTICS_DB', str(tmp_path / 'ui.sqlite3'))
    app = AppTest.from_file(ROOT / 'app.py', default_timeout=30).run()
    assert not app.exception
    app.sidebar.radio[0].set_value('Analytics Request').run()
    app.text_area[0].set_value('Kerendia Commercial Reach Index Global').run()
    app.checkbox[0].check().run()
    next(b for b in app.button if b.label == 'Generate recommendation').click().run()
    assert not app.exception and any('BUILD NEW' in s.value for s in app.success)
    app.sidebar.radio[0].set_value('Decision Explanation').run()
    assert not app.exception
    assert any(s.value == 'BUILD NEW' for s in app.subheader)
    app.sidebar.radio[0].set_value('Approvals').run()
    app.text_input[0].set_value('UI reviewer')
    app.text_area[0].set_value('Owner confirmed scope for demonstration.')
    app.checkbox[0].check()
    next(b for b in app.button if b.label == 'Record review').click().run()
    assert not app.exception
    app.sidebar.radio[0].set_value('Asset Explorer').run()
    assert not app.exception
    # New app session reads the same SQLite file, proving persistence across UI restart.
    restart = AppTest.from_file(ROOT / 'app.py', default_timeout=30).run()
    restart.sidebar.radio[0].set_value('Approvals').run()
    assert not restart.exception
    assert 'approved' in restart.dataframe[0].value['status'].tolist()


def test_confirmation_resets_and_human_review_controls(tmp_path, monkeypatch):
    monkeypatch.setenv('GOVERNED_ANALYTICS_DB', str(tmp_path / 'clarify.sqlite3'))
    app = AppTest.from_file(ROOT / 'app.py', default_timeout=30).run()
    app.sidebar.radio[0].set_value('Analytics Request').run()
    assert next(b for b in app.button if b.label == 'Generate recommendation').disabled
    app.text_area[0].set_value('Kerendia Commercial Reach Index Global').run()
    app.checkbox[0].check().run()
    assert not next(b for b in app.button if b.label == 'Generate recommendation').disabled
    app.text_area[0].set_value('Nubeqa sales').run()
    assert not app.checkbox[0].value
    assert next(b for b in app.button if b.label == 'Generate recommendation').disabled
    app.selectbox[0].set_value('REQ-0001').run()
    app.checkbox[0].check().run()
    next(b for b in app.button if b.label == 'Generate recommendation').click().run()
    assert any('HUMAN REVIEW' in s.value for s in app.success)
    app.sidebar.radio[0].set_value('Approvals').run()
    outcome = next(s for s in app.selectbox if s.label == 'Review outcome')
    assert 'approved' not in outcome.options
    assert not app.exception


def test_pbip_export_after_real_fix_approval(tmp_path, monkeypatch):
    monkeypatch.setenv('GOVERNED_ANALYTICS_DB', str(tmp_path / 'export.sqlite3'))
    app = AppTest.from_file(ROOT / 'app.py', default_timeout=30).run()
    app.sidebar.radio[0].set_value('Analytics Request').run()
    app.text_area[0].set_value('Kerendia Inventory Coverage Italy').run()
    app.checkbox[0].check().run()
    next(b for b in app.button if b.label == 'Generate recommendation').click().run()
    assert any('FIX' in s.value for s in app.success)
    app.sidebar.radio[0].set_value('Approvals').run()
    assert not any(b.label == 'Prepare Power BI project ZIP' for b in app.button)
    app.text_input[0].set_value('Export demo reviewer')
    app.text_area[0].set_value('Synthetic draft for the existing owner. Remediation remains a prerequisite.')
    for box in app.checkbox: box.check()
    next(b for b in app.button if b.label == 'Record review').click().run()
    next(b for b in app.button if b.label == 'Prepare Power BI project ZIP').click().run()
    assert not app.exception and not app.error
    assert any(b.label == 'Download Power BI project (.pbip ZIP)' for b in app.get('download_button'))
