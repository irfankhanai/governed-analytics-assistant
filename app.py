"""Thin Streamlit UI. All decision logic lives in src/."""
import json
import os
import hashlib
from pathlib import Path
import pandas as pd
import streamlit as st
from src.data_loader import load_data, load_config, ROOT, DEFAULT_DATA
from src.data_validation import validate_data
from src.request_parser import parse_request
from src.asset_matching import detect_duplicates
from src.governance_engine import check_governance, evaluate_retirement_risk
from src.recommendation_engine import generate_recommendation
from src.database import save_decision, list_decisions, get_decision
from src.approvals import review_decision
from src.explanations import decision_report
from src.presentation import requirements_rows, candidate_rows, decision_summary, score_rows
from src.pbip_export import prepare_export, export_pbip

st.set_page_config(page_title='Governed Analytics', page_icon='◈', layout='wide')
DB = Path(os.environ.get('GOVERNED_ANALYTICS_DB', str(ROOT / 'runtime' / 'decisions.sqlite3')))


@st.cache_data
def read_sources(modified):
    return load_data()


@st.cache_data
def duplicate_pairs(data, config):
    return detect_duplicates(data, config)


def frame(rows):
    return pd.DataFrame(rows).drop(columns=['_sheet', '_row'], errors='ignore')


def show_candidate(c, saved_config):
    st.write(' · '.join(c['match_reasons']))
    st.caption('Calculated score = sum of weighted points below. It ranks matches; it is not a probability. Missing evidence and governance checks take priority over the score.')
    st.dataframe(score_rows(c, saved_config), hide_index=True)
    st.dataframe([{k: v for k, v in rule.items() if k not in ['source_rule', 'implementation']} for rule in c['governance']['checks']], hide_index=True)
    for message in c['governance']['missing']: st.warning('Missing evidence: ' + message)
    for message in c['governance']['risks']: st.warning(message)
    st.caption('Source facts: original workbook records below include their sheet and Excel row number.')
    st.json(c['governance']['evidence'], expanded=False)


def show_summary(result):
    summary = decision_summary(result)
    st.write(summary['meaning'])
    st.write('**Why this action:**')
    for reason in result['reasons']: st.write('• ' + reason)
    st.write('**Responsible owner:** ' + summary['owner'])
    if summary['unanswered']:
        st.warning('Needs clarification:\n\n' + '\n\n'.join(summary['unanswered']))
    if result.get('risks'):
        with st.expander('Risks to address before execution', expanded=True):
            for risk in result['risks']: st.write('• ' + risk)
    st.write('**Next action:** ' + summary['next_step'])


try:
    data = read_sources(DEFAULT_DATA.stat().st_mtime_ns)
    cfg = load_config()
    validation = validate_data(data)
except Exception as exc:
    st.error(f'Cannot load source data or configuration: {exc}')
    st.stop()

st.title('Governed Analytics Decision Assistant')
st.caption('Bayer challenge · Since AI 2026 · Local prototype')
st.info('All workbook records are synthetic / illustrative. They are not actual Bayer performance data. No production BI systems are connected.')
page = st.sidebar.radio('Workspace', ['Overview', 'Analytics Request', 'Decision Explanation', 'Approvals', 'Asset Explorer'])
st.sidebar.caption('Deterministic rules · No API key required')
with st.sidebar.expander('Scoring configuration'):
    st.json(cfg)
    st.caption('Edit config/rules.yaml to change weights and thresholds. Saved decisions retain their original configuration.')

if page == 'Overview':
    st.header('Understand the estate before building')
    st.write('**1. Describe the request → 2. Inspect the recommendation → 3. Record a human review.**')
    st.caption('Start in Analytics Request. The assistant recommends what to do; your BI team carries out approved work.')
    with st.expander('What the six actions mean'):
        from src.presentation import ACTION_GUIDANCE
        st.dataframe([{'Action': k, 'Meaning': v} for k, v in ACTION_GUIDANCE.items()], hide_index=True)
    duplicates = duplicate_pairs(data, cfg)
    cols = st.columns(4)
    for col, label, value in zip(cols, ['Analytics assets', 'KPI definitions', 'Governance signals', 'Potential duplicate pairs'],
                                [len(data['Analytics_Assets']), len(data['KPI_Catalog']), len(data['Governance_Signals']), len(duplicates)]):
        col.metric(label, value)
    left, right = st.columns(2)
    left.subheader('Platforms')
    left.dataframe(frame(data['Analytics_Assets'])['platform'].value_counts().rename('Assets'))
    right.subheader('Lifecycle')
    right.dataframe(frame(data['Analytics_Assets'])['lifecycle_status'].value_counts().rename('Assets'))
    st.subheader('Potential overlap')
    st.caption('Equal product and market scope; canonical KPI Jaccard overlap meets the configured threshold. Business purpose still needs confirmation.')
    st.dataframe(duplicates, hide_index=True)
    st.subheader('Data validation')
    st.write(f'{len(validation)} findings. Source data is never repaired automatically.')
    if validation: st.dataframe(validation, hide_index=True)
    with st.expander('Source governance rules and definitions'):
        st.dataframe(frame(data['Governance_Rules']), hide_index=True)
        st.dataframe(frame(data['Data_Dictionary']), hide_index=True)
    st.caption(f"Source SHA-256: {data['_meta']['sha256']}")

elif page == 'Analytics Request':
    st.header('Find a governed way to answer the question')
    options = ['New request'] + [r['request_id'] for r in data['Business_Requests']]
    selected = st.selectbox('Request source', options)
    source = next((r for r in data['Business_Requests'] if r['request_id'] == selected), None)
    source_key = selected
    text = st.text_area('Business request', value=source['request_text'] if source else '', key='text_' + source_key,
                        placeholder='Show Nubeqa sales growth and forecast variance in Germany.')
    products = ['Auto-detect'] + [r['product_name'] for r in data['Products']] + ['All Pharma']
    markets = ['Auto-detect', 'Global'] + sorted({r['region'] for r in data['Markets']}) + [r['market_id'] for r in data['Markets']]
    left, right = st.columns(2)
    product = left.selectbox('Product scope', products, index=products.index(source['product_context']) if source else 0, key='product_' + source_key)
    market = right.selectbox('Market scope', markets, index=markets.index(source['market_context']) if source else 0, key='market_' + source_key)
    metrics = sorted({r['canonical_metric'] for r in data['KPI_Catalog']})
    kpis = st.multiselect('Required canonical KPIs (leave empty to extract from text)', metrics, key='kpis_' + source_key)
    purpose = st.text_input('What decision will this help you make? (optional)', key='purpose_' + source_key,
                            help='Purpose is recorded. Matching currently compares its words with asset titles; it does not interpret meaning.')
    with st.expander('Optional platform and model constraints'):
        platform = st.selectbox('Required platform', ['Any'] + sorted({r['platform'] for r in data['Analytics_Assets']}))
        model_id = st.selectbox('Required semantic model', ['Any'] + [r['model_id'] for r in data['Semantic_Models']])
    clarification = st.text_area('Clarification note (explicitly explain any override of text versus selected fields)', key='clarification_' + source_key)
    request = parse_request(data, text, None if product == 'Auto-detect' else product,
                            None if market == 'Auto-detect' else market, kpis or None, purpose,
                            source['request_id'] if source else None,
                            None if platform == 'Any' else platform, None if model_id == 'Any' else model_id, clarification)
    request['source_record'] = source
    st.subheader('Review interpreted requirements')
    st.dataframe(requirements_rows(request), hide_index=True)
    st.caption('Interpretation uses catalogue names and explicit selections. Check that all requested KPIs are included.')
    for missing in request['missing']: st.warning(missing)
    for conflict in request['unresolved_conflicts']: st.warning(conflict)
    if clarification and request['conflicts']: st.info('Your clarification will be recorded as a human scope override. Check the selected fields before continuing.')
    with st.expander('Extraction details and original source request'):
        st.json({'extracted': request['extracted'], 'conflicts': request['conflicts'], 'source_record': source})
    fingerprint = hashlib.sha256(json.dumps({k: v for k, v in request.items() if k != 'request_id'}, sort_keys=True).encode()).hexdigest()
    if st.session_state.get('request_fingerprint') != fingerprint:
        st.session_state['requirements_confirmed'] = False
        st.session_state['request_fingerprint'] = fingerprint
    confirmed = st.checkbox('I have reviewed the requirements and any unresolved questions', key='requirements_confirmed')
    if st.button('Generate recommendation', type='primary', disabled=not confirmed):
        request['requirements_reviewed'] = True
        with st.spinner('Checking inventory, rules and evidence…'):
            result = generate_recommendation(data, request, cfg)
            decision_id = save_decision(DB, result)
            st.session_state['decision_id'] = decision_id
        st.success(f"{result['action']} · saved as {decision_id}. Open Decision Explanation to inspect evidence, then Approvals to review.")
        show_summary(result)

elif page == 'Decision Explanation':
    st.header('Follow the evidence')
    decisions = list_decisions(DB)
    if not decisions:
        st.info('Generate a recommendation on Analytics Request first.')
    else:
        ids = [r['id'] for r in decisions]
        chosen = st.selectbox('Saved decision', ids, index=ids.index(st.session_state.get('decision_id')) if st.session_state.get('decision_id') in ids else 0)
        record = get_decision(DB, chosen)
        r = record['snapshot']
        st.subheader(r['action'])
        st.write(r['request']['text'])
        st.caption(f"{r['scope'].capitalize()} recommendation · {record['status']} · configuration {r['config']['version']}")
        show_summary(r)
        st.write('Selected assets:', ', '.join(r['asset_ids']) or 'None')
        st.subheader('Existing assets: coverage and gaps')
        st.dataframe(candidate_rows(r), hide_index=True)
        with st.expander('Why alternatives were not selected'):
            st.dataframe(r['alternatives'], hide_index=True)
        for c in r['candidates']:
            with st.expander(f"{c['asset']['asset_id']} · {c['asset']['asset_name']} · score {c['score']}"):
                show_candidate(c, r['config'])
        with st.expander('Semantic models considered for reuse'):
            st.dataframe(frame(r['model_candidates']), hide_index=True)
        with st.expander('Separate portfolio lifecycle findings'):
            st.caption('These do not change the request recommendation. Submit an individual proposal from Asset Explorer.')
            st.json(r['portfolio'], expanded=False)
        with st.expander('Assumptions, original inputs and configuration'):
            st.write(r['assumptions'])
            st.json(r['request'])
            st.json(r['config'])
        if 'draft_specification' in r:
            st.subheader('Draft analytics specification')
            st.json(r['draft_specification'])
        st.caption('Approval records a proposal. It does not implement a change or verify that remediation is complete.')
        st.download_button('Download decision report', decision_report(record), f'{chosen}.md', 'text/markdown')
        st.download_button('Download evidence JSON', json.dumps(record, indent=2), f'{chosen}.json', 'application/json')

elif page == 'Approvals':
    st.header('Human review')
    st.caption('Demo identities only. This is not enterprise authentication. Approval records a proposal and never changes a BI asset.')
    decisions = list_decisions(DB)
    st.dataframe(decisions, hide_index=True)
    if decisions:
        decision_id = st.selectbox('Decision to review', [r['id'] for r in decisions])
        record = get_decision(DB, decision_id)
        st.subheader(record['snapshot']['action'])
        st.write(record['snapshot']['request']['text'])
        show_summary(record['snapshot'])
        with st.expander('Review complete evidence before responding'):
            st.json(record['snapshot'], expanded=False)
        if record['status'] == 'pending':
            with st.form('review'):
                reviewer = st.text_input('Demo reviewer identity')
                outcomes = ['changes_requested', 'rejected'] if record['action'] == 'HUMAN REVIEW' else ['approved', 'rejected', 'changes_requested']
                status = st.selectbox('Review outcome', outcomes)
                comments = st.text_area('Reviewer comments and conditions')
                owner = st.checkbox('Accountable owner has reviewed the proposal')
                dependencies = impact = remediation = False
                if record['action'] in ['CONSOLIDATE', 'RETIRE']:
                    dependencies = st.checkbox('Dependencies and lineage completeness have been checked')
                    impact = st.checkbox('Business impact and replacement suitability have been checked')
                if record['snapshot'].get('risks'):
                    remediation = st.checkbox('A remediation plan addresses flagged risks')
                if st.form_submit_button('Record review'):
                    try:
                        review_decision(DB, decision_id, status, reviewer, comments,
                                        dict(owner_review=owner, dependency_check=dependencies, business_impact=impact, remediation_plan=remediation))
                        st.success('Review saved.')
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
        st.subheader('Audit history')
        st.dataframe(record['reviews'], hide_index=True)
        st.download_button('Download final decision report', decision_report(record), f'{decision_id}.md', 'text/markdown')
        with st.expander('Optional final step: Power BI project draft'):
            st.caption('Separate export only. The request, recommendation and approval workflow stays unchanged.')
            prepared = prepare_export(record, data)
            if prepared['errors']:
                for reason in prepared['errors']: st.info(reason)
            else:
                st.write(f"{len(prepared['rows'])} synthetic source rows. Two pages: review notes and a data table.")
                st.dataframe(prepared['mappings'], hide_index=True)
                st.warning('Draft export: project schemas and references are checked. Opening, refreshing and rendering in Power BI Desktop still require verification.')
                st.caption('Includes all available months for the selected product/market; text time filters are not interpreted. No aggregation or invented KPI measures. Unsupported KPIs block export. For FIX, this is a draft for the existing asset owner, not a replacement operation.')
                if st.button('Prepare Power BI project ZIP', key='pbip_' + decision_id):
                    try:
                        package = export_pbip(record, data)
                        st.download_button('Download Power BI project (.pbip ZIP)', package,
                                           f'{decision_id}-PowerBI.zip', 'application/zip')
                        st.info('Extract the entire ZIP, open Governed.pbip in Power BI Desktop, then click Refresh to load the embedded synthetic snapshot.')
                    except Exception as exc:
                        st.error(f'Export could not be validated: {exc}. Your saved decision and approval are unchanged.')

elif page == 'Asset Explorer':
    st.header('Inspect an existing asset')
    search = st.text_input('Search asset name or ID')
    platform = st.selectbox('Platform filter', ['All'] + sorted({a['platform'] for a in data['Analytics_Assets']}))
    assets = [a for a in data['Analytics_Assets'] if search.lower() in (a['asset_id'] + ' ' + a['asset_name']).lower() and (platform == 'All' or a['platform'] == platform)]
    st.dataframe(frame(assets), hide_index=True)
    if assets:
        aid = st.selectbox('Asset', [a['asset_id'] for a in assets])
        a = next(a for a in assets if a['asset_id'] == aid)
        g = check_governance(data, a, cfg)
        st.subheader(a['asset_name'])
        st.dataframe([{k: v for k, v in c.items() if k not in ['source_rule', 'implementation']} for c in g['checks']], hide_index=True)
        st.json(g, expanded=False)
        retirement = evaluate_retirement_risk(data, dict(asset=a, governance=g), duplicate_pairs(data, cfg), cfg)
        st.subheader('Portfolio retirement safeguards')
        st.json(retirement)
        if st.button('Submit portfolio lifecycle proposal'):
            req = parse_request(data, 'Portfolio lifecycle assessment for ' + aid, a['product_scope'], a['market_scope'],
                                sorted({k['canonical_metric'] for k in g['evidence']['kpis']}))
            result = dict(request=req, action=retirement['action'], scope='portfolio', asset_ids=[aid],
                          reasons=[f'{k}: {v}' for k, v in retirement['checks'].items()], risks=g['risks'],
                          candidates=[], alternatives=[], portfolio=[retirement], model_candidates=[],
                          source=data['_meta'], config=cfg, validation=validation, approval_status='pending',
                          assumptions=['No recorded downstream edge is not proof of dependency completeness.'],
                          next_steps=retirement['next_steps'], evidence=g)
            saved = save_decision(DB, result)
            st.session_state['decision_id'] = saved
            st.success(f'Saved {saved}. Review in Approvals.')
