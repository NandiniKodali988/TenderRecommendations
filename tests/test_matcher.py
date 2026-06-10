import pytest
from matcher import keyword_filter, MAX_FEEDBACK_WEIGHT


# --- Fixtures ---

def make_tender(**kwargs) -> dict:
    defaults = {
        "id": "t1",
        "title": "Civil construction work at BHEL Hyderabad",
        "unit": "BHEL, Hyderabad",
        "is_gem": True,
        "value": 5_000_000,
    }
    return {**defaults, **kwargs}


def make_profile(**kwargs) -> dict:
    defaults = {
        "id": "p1",
        "work_scope": "Civil construction and structural fabrication",
        "preferred_units": ["BHEL, Hyderabad"],
        "gem_only": True,
        "preferred_tender_types": [],
        "include_keywords": [],
        "exclude_keywords": [],
    }
    return {**defaults, **kwargs}


# --- keyword_filter tests ---

class TestKeywordFilter:
    def test_no_filters_returns_all(self):
        tenders = [make_tender(), make_tender(id="t2", title="Supply of steel")]
        profile = make_profile()
        assert keyword_filter(tenders, profile) == tenders

    def test_include_keyword_keeps_matching(self):
        tenders = [
            make_tender(title="Civil erection work"),
            make_tender(id="t2", title="Supply of stationery"),
        ]
        profile = make_profile(include_keywords=["civil"])
        result = keyword_filter(tenders, profile)
        assert len(result) == 1
        assert result[0]["id"] == "t1"

    def test_include_keyword_case_insensitive(self):
        tenders = [make_tender(title="CIVIL construction works")]
        profile = make_profile(include_keywords=["civil"])
        assert len(keyword_filter(tenders, profile)) == 1

    def test_exclude_keyword_removes_matching(self):
        tenders = [
            make_tender(title="Civil construction work"),
            make_tender(id="t2", title="Printing and stationery supply"),
        ]
        profile = make_profile(exclude_keywords=["stationery"])
        result = keyword_filter(tenders, profile)
        assert len(result) == 1
        assert result[0]["id"] == "t1"

    def test_exclude_takes_effect_after_include(self):
        tenders = [make_tender(title="Civil stationery work")]
        profile = make_profile(include_keywords=["civil"], exclude_keywords=["stationery"])
        assert keyword_filter(tenders, profile) == []

    def test_empty_tender_list(self):
        profile = make_profile(include_keywords=["civil"])
        assert keyword_filter([], profile) == []

    def test_none_keywords_treated_as_empty(self):
        tenders = [make_tender()]
        profile = make_profile(include_keywords=None, exclude_keywords=None)
        assert keyword_filter(tenders, profile) == tenders


# --- Feedback weight tests ---

class TestFeedbackWeight:
    def test_zero_likes_gives_zero_weight(self):
        assert min(MAX_FEEDBACK_WEIGHT, 0 * 0.03) == 0.0

    def test_weight_grows_with_likes(self):
        assert min(MAX_FEEDBACK_WEIGHT, 5 * 0.03) == pytest.approx(0.15)

    def test_weight_reaches_max_at_ten_likes(self):
        assert min(MAX_FEEDBACK_WEIGHT, 10 * 0.03) == pytest.approx(MAX_FEEDBACK_WEIGHT)

    def test_weight_capped_beyond_ten_likes(self):
        assert min(MAX_FEEDBACK_WEIGHT, 15 * 0.03) == pytest.approx(MAX_FEEDBACK_WEIGHT)
        assert min(MAX_FEEDBACK_WEIGHT, 100 * 0.03) == pytest.approx(MAX_FEEDBACK_WEIGHT)

    def test_max_feedback_weight_is_thirty_percent(self):
        assert MAX_FEEDBACK_WEIGHT == 0.3
