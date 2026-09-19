from xray.score.config import ScoreConfig


def fit_reference_bundle(panel, config=None):
    from xray.score.core import fit_reference_bundle as fit
    return fit(panel, config)


def score_panel(panel, reference):
    from xray.score.core import score_panel as predict
    return predict(panel, reference)


def run(*args, **kwargs):
    from xray.score.pipeline import run as execute
    return execute(*args, **kwargs)
