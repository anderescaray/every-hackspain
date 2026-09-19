import json
from pathlib import Path

import pandas as pd
import pytest

from test_score_pipeline import score_fixture
from xray.artifacts import sha256
from xray.score import ScoreConfig
from xray.score.pipeline import run, validate_saved_scores


def save_features(directory: Path, panel, name='company_monthly_features.parquet'):
    directory.mkdir(parents=True)
    path = directory / name
    panel.to_parquet(path, index=False)
    (directory / '_feature_manifest.json').write_text(
        json.dumps({'outputs_sha256': {name: sha256(path)}}), encoding='utf-8')


def test_fit_predict_publish_and_validate(tmp_path):
    source = tmp_path / 'visible'
    panel = score_fixture()
    save_features(source, panel)
    report = run(source, verbose=False)
    assert report['holdout_group_count'] == 1
    output = source / 'scores'
    assert validate_saved_scores(output, source, prefix_month='2025-06-01')['rows'] == len(panel)
    reference = output / '_company_score_reference.json'
    reference_hash = sha256(reference)
    hidden = tmp_path / 'hidden'
    unseen = panel.loc[panel.company_id.eq('C0')].assign(company_id='NEW', group_id='UNSEEN')
    save_features(hidden, unseen)
    prediction = run(hidden, mode='predict', reference_file=reference, verbose=False)
    assert prediction['cohorts']['unseen']['rows'] == 12
    assert sha256(reference) == reference_hash
    assert validate_saved_scores(hidden / 'scores', hidden)['rows'] == 12
    copied_reference = hidden / 'scores' / '_company_score_reference.json'
    assert json.loads(copied_reference.read_text()) == json.loads(reference.read_text())
    before = json.loads((output / '_company_score_manifest.json').read_text())['outputs_sha256']
    run(source, verbose=False)
    after = json.loads((output / '_company_score_manifest.json').read_text())['outputs_sha256']
    assert before == after
    scores_path = output / 'company_monthly_scores.parquet'
    scores = pd.read_parquet(scores_path)
    scores.loc[0, 'score'] = 42
    scores.to_parquet(scores_path, index=False)
    with pytest.raises(ValueError, match='Hash de score'):
        validate_saved_scores(output, source)


def test_predict_requires_reference(tmp_path):
    with pytest.raises(ValueError, match='referencia'):
        run(tmp_path, mode='predict', verbose=False)


def test_group_currency_pipeline(tmp_path):
    p = score_fixture().loc[lambda frame: frame.company_id.isin(['C0', 'C2', 'C4', 'C6', 'C8'])]
    p = p.drop(columns='company_id').reset_index(drop=True)
    source = tmp_path / 'group'
    save_features(source, p, 'group_currency_monthly_features.parquet')
    report = run(source, config=ScoreConfig(panel='group_currency'), verbose=False)
    assert report['latest']['rows'] == 5
    assert validate_saved_scores(source / 'scores', source, panel='group_currency')['entities'] == 5


def test_latest_keeps_missing_scores_without_stale_imputation(tmp_path):
    p = score_fixture()
    mask = p.company_id.eq('C0') & p.month.eq(p.month.max())
    p.loc[mask, ['tx_count', 'tx_usable_count']] = 0
    source = tmp_path / 'features'
    save_features(source, p)
    run(source, verbose=False)
    latest = pd.read_csv(source / 'scores' / 'company_latest_scores.csv')
    row = latest.loc[latest.company_id.eq('C0')].iloc[0]
    assert pd.isna(row.score)
    assert row.is_stale
    assert row.last_scored_month.startswith('2025-11-01')


def test_invalid_feature_hash_is_rejected(tmp_path):
    source = tmp_path / 'bad'
    save_features(source, score_fixture())
    (source / '_feature_manifest.json').write_text(json.dumps({'outputs_sha256': {}}))
    with pytest.raises(ValueError, match='manifiesto'):
        run(source, verbose=False)


def test_latest_preserves_entity_missing_from_final_month(tmp_path):
    p = score_fixture()
    p = p.loc[~(p.company_id.eq('C0') & p.month.eq(p.month.max()))]
    p.loc[p.company_id.eq('C2'), ['tx_count', 'tx_usable_count']] = 0
    source = tmp_path / 'features'
    save_features(source, p)
    run(source, verbose=False)
    latest = pd.read_csv(source / 'scores' / 'company_latest_scores.csv').set_index('company_id')
    assert len(latest) == 10
    assert pd.isna(latest.loc['C0', 'score'])
    assert not latest.loc['C0', 'current_month_present']
    assert latest.loc['C0', 'staleness_status'] == 'stale'
    assert latest.loc['C2', 'staleness_status'] == 'never_scored'


def test_predict_keeps_reference_bytes_even_with_different_json_format(tmp_path):
    source = tmp_path / 'features'
    save_features(source, score_fixture())
    run(source, verbose=False)
    reference = json.loads((source / 'scores' / '_company_score_reference.json').read_text())
    compact = tmp_path / 'compact-reference.json'
    compact.write_text(json.dumps(reference, separators=(',', ':')), encoding='utf-8')
    output = source / 'predicted'
    run(source, output, mode='predict', reference_file=compact, verbose=False)
    assert sha256(compact) == sha256(output / '_company_score_reference.json')
    assert validate_saved_scores(output, source)['scored_rows'] == 120
