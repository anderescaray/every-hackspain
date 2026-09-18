import os

import pytest

from xray.artifacts import check_output_path, publish_bundle


def test_output_must_not_overlap_input(tmp_path):
    source = tmp_path / 'raw'
    for output in (source, source / 'sub', tmp_path):
        with pytest.raises(ValueError, match='solapa'):
            check_output_path(output, source)


def test_publication_preserves_old_and_unrelated_files(tmp_path):
    staged, output = tmp_path / 'stage', tmp_path / 'out'
    staged.mkdir()
    output.mkdir()
    (staged / 'data').write_text('new')
    (staged / 'manifest').write_text('new manifest')
    (output / 'data').write_text('old')
    (output / 'unrelated').write_text('keep')
    publish_bundle(staged, output, 'manifest')
    assert (output / 'data').read_text() == 'new'
    assert (output / 'unrelated').read_text() == 'keep'
    assert next((output / '.history').glob('*/data')).read_text() == 'old'
    assert not (output / '.pipeline.lock').exists()


def test_publication_rolls_back_on_failure(tmp_path, monkeypatch):
    staged, output = tmp_path / 'stage', tmp_path / 'out'
    staged.mkdir()
    output.mkdir()
    for name in ('data', 'manifest'):
        (staged / name).write_text('new')
        (output / name).write_text('old')
    replace = os.replace

    def fail_on_manifest(source, target):
        if source == staged / 'manifest':
            raise OSError('simulated failure')
        replace(source, target)

    monkeypatch.setattr(os, 'replace', fail_on_manifest)
    with pytest.raises(OSError, match='simulated'):
        publish_bundle(staged, output, 'manifest')
    assert (output / 'data').read_text() == 'old'
    assert (output / 'manifest').read_text() == 'old'
    assert not (output / '.pipeline.lock').exists()
