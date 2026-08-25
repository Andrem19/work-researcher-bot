from work_researcher.browser import _MODAL_TAGGER_JS


def test_modal_snapshot_clears_background_element_numbers() -> None:
    clear = "document.querySelectorAll('[data-wr-n]').forEach"
    dialogs = "const dialogs = Array.from"

    assert clear in _MODAL_TAGGER_JS
    assert _MODAL_TAGGER_JS.index(clear) < _MODAL_TAGGER_JS.index(dialogs)
