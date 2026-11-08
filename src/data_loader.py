"""Read-only workbook ingestion. Source rows retain Excel row provenance."""
from pathlib import Path
import hashlib
import json
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / 'Bayer_Pharmaceuticals_SinceAI_2026_FINAL_Builder_Data_Pack.xlsx'


def load_data(path=DEFAULT_DATA):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f'Workbook not found: {path}')
    frames = pd.read_excel(path, sheet_name=None)
    tables = {}
    for sheet, frame in frames.items():
        frame = frame.astype(object).where(frame.notna(), None)
        records = json.loads(frame.to_json(orient='records', date_format='iso'))
        for i, row in enumerate(records, 2):
            row['_sheet'] = sheet
            row['_row'] = i
        tables[sheet] = records
    tables['_meta'] = {'filename': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    return tables


def load_config(path=ROOT / 'config' / 'rules.yaml'):
    config = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    weights = config['weights']
    expected = {'product', 'market', 'kpi', 'purpose', 'governance', 'freshness', 'usage'}
    if set(weights) != expected or any(v < 0 for v in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError('Scoring weights must be nonnegative and include all seven dimensions.')
    t = config['thresholds']
    if not 0 <= t['reuse_score'] <= 100 or not 0 < t['duplicate_jaccard'] <= 1 or not 0 < t['minimum_kpi_coverage'] <= 1:
        raise ValueError('Invalid score or coverage threshold.')
    if t['usage_months'] < 1 or t['low_monthly_users'] < 0:
        raise ValueError('Invalid usage thresholds.')
    config['hash'] = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    return config


def index(data, sheet, key):
    return {r[key]: r for r in data.get(sheet, [])}


def related(data, sheet, key, value):
    return [r for r in data.get(sheet, []) if r.get(key) == value]
