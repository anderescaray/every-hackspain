import json

import pandas as pd
import pytest

from test_clean import row
from test_features import fixture_tables
from xray.artifacts import sha256
from xray.features import FeatureConfig, run
from xray.features.validation import validate_saved_features


def test_end_to_end_publication_manifest_and_prefix(tmp_path):
    cleaned, processed = tmp_path / 'cleaned', tmp_path / 'processed'
    cleaned.mkdir()
    tables = fixture_tables([row(i, date=f'2025-{i:02d}-10', amount=float(i)) for i in range(1, 7)])
    for name, frame in tables.items():
        frame.to_parquet(cleaned / f'{name}.parquet', index=False)
    hashes = {path.name: sha256(path) for path in cleaned.iterdir()}
    (cleaned / '_manifest.json').write_text(json.dumps({'outputs_sha256': hashes}), encoding='utf-8')
    config = FeatureConfig(start_month='2025-01-01', end_month='2025-06-01')
    run(cleaned, processed, config, verbose=False)
    result = validate_saved_features(processed, cleaned, prefix_month='2025-03-01')
    assert result['rows'] == 12
    assert result['model_candidates'] > 30
    original = json.loads((processed / '_feature_manifest.json').read_text())['outputs_sha256']
    run(cleaned, processed, config, verbose=False)
    repeated = json.loads((processed / '_feature_manifest.json').read_text())['outputs_sha256']
    assert original == repeated
    panel = pd.read_parquet(processed / 'company_monthly_features.parquet')
    panel.loc[0, 'tx_inflow'] = -123
    panel.to_parquet(processed / 'company_monthly_features.parquet', index=False)
    with pytest.raises(ValueError, match='Hash incorrecto'):
        validate_saved_features(processed, cleaned)
