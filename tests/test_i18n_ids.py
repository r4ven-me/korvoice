import pytest

from korvoice.i18n import _EN, _RU, set_language, tr


@pytest.fixture(autouse=True)
def reset_language_override():
    set_language("system")
    yield
    set_language("system")


def test_every_id_style_key_has_both_languages():
    # Short ids stand in for long texts; each one needs an English text as
    # well, or the English UI shows the bare id.
    for key in _EN:
        assert key in _RU, key


@pytest.mark.parametrize("key", sorted(_EN))
def test_english_id_translates_to_text(key):
    set_language("en")
    assert tr(key) != key
