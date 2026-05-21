from app.services.audit import extract_contacts
from app.services.scoring import hotness, score_lead


def test_no_website_high_review_is_hot():
    flags = [{"key": "no_website", "failed": True}]
    score = score_lead(flags, review_count=47, rating=4.6)
    assert score >= 90
    assert hotness(score) == "hot"


def test_broken_site_is_hot():
    flags = [{"key": "broken_site", "failed": True}, {"key": "no_ssl", "failed": True}]
    assert score_lead(flags, 30, 4.2) >= 80


def test_clean_site_is_cold():
    flags = [{"key": "no_ssl", "failed": False}]
    assert score_lead(flags, 200, 4.9) < 30


def test_hotness_thresholds():
    assert hotness(85) == "hot"
    assert hotness(65) == "warm"
    assert hotness(30) == "cold"
    assert hotness(None) == "unknown"


def test_extract_contacts():
    html = (
        '<a href="mailto:owner@biz.com">mail</a>'
        '<a href="https://facebook.com/biz">fb</a>'
        '<a href="https://instagram.com/biz?ref=x">ig</a>'
    )
    c = extract_contacts(html)
    assert c["email"] == "owner@biz.com"
    assert "https://facebook.com/biz" in c["socials"]
    assert "https://instagram.com/biz" in c["socials"]


def test_extract_contacts_skips_assets():
    assert extract_contacts('img@2x.png in text')["email"] is None
    assert extract_contacts("")["email"] is None
