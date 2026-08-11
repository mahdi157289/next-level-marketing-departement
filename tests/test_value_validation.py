# tests/test_value_validation.py
from crm.value_validation import is_unrealistic_value


def test_numeric_ranges():
    assert is_unrealistic_value("rating", 6)
    assert is_unrealistic_value("rating", 5.1)
    assert not is_unrealistic_value("rating", 4.5)
    assert is_unrealistic_value("seo_score", 120)
    assert not is_unrealistic_value("seo_score", 0)
    assert is_unrealistic_value("review_count", -3)
    assert not is_unrealistic_value("review_count", 12)
    assert is_unrealistic_value("review_count", 2_000_000)


def test_placeholders_flag_any_string_field():
    for field in ("industry", "country", "email", "hours", "business_type"):
        assert is_unrealistic_value(field, "N/A"), field
        assert is_unrealistic_value(field, "unknown"), field
    assert not is_unrealistic_value("industry", "Software")


def test_email_and_phone_shape():
    assert is_unrealistic_value("email", "hello@acme")
    assert is_unrealistic_value("email", "hello @acme.tn")
    assert is_unrealistic_value("email", "x@example.com")
    assert not is_unrealistic_value("email", "hello@acme.tn")
    assert is_unrealistic_value("phone", "123")
    assert is_unrealistic_value("phone", "+216 CALL ME")
    assert not is_unrealistic_value("phone", "+216 71 123 456")


def test_hours_requires_time_like_text():
    assert is_unrealistic_value("hours", "00")
    assert is_unrealistic_value("hours", "a")
    assert not is_unrealistic_value("hours", "Mon-Fri 9:00-18:00")
    assert not is_unrealistic_value("hours", "Open 24h")


def test_country_alpha_only():
    assert is_unrealistic_value("country", "123TR")
    assert is_unrealistic_value("country", "T")
    assert not is_unrealistic_value("country", "Tunisia")


def test_short_text_fields():
    assert is_unrealistic_value("industry", "x")
    assert is_unrealistic_value("business_type", "n/a")
    assert is_unrealistic_value("address", "Tunis")
    assert not is_unrealistic_value("address", "Avenue Habib Bourguiba, Tunis")
    assert is_unrealistic_value("description", "short")


def test_socials_plausible():
    assert is_unrealistic_value("facebook", "facebook")
    assert is_unrealistic_value("instagram", "instagram")
    assert is_unrealistic_value("linkedin", "/")
    assert not is_unrealistic_value("facebook", "https://facebook.com/acme")
    assert not is_unrealistic_value("twitter", "@acme")


def test_unknown_fields_never_flagged():
    assert not is_unrealistic_value("name", "whatever")
    assert not is_unrealistic_value("lead_score", "whatever")
    assert not is_unrealistic_value("id", "n/a")