from pathlib import Path

from aelyn.core.seen_offers import SeenOffers


def test_filter_new_returns_all_ids_the_first_time(tmp_path: Path):
    seen = SeenOffers(tmp_path / "seen_offers.db")

    new_ids = seen.filter_new(["1", "2", "3"])

    assert new_ids == ["1", "2", "3"]


def test_filter_new_excludes_already_seen_ids_on_a_later_call(tmp_path: Path):
    seen = SeenOffers(tmp_path / "seen_offers.db")
    seen.filter_new(["1", "2"])

    new_ids = seen.filter_new(["2", "3"])

    assert new_ids == ["3"]


def test_filter_new_deduplicates_a_repeated_id_within_one_call(tmp_path: Path):
    seen = SeenOffers(tmp_path / "seen_offers.db")

    new_ids = seen.filter_new(["1", "1", "2"])

    assert new_ids == ["1", "2"]


def test_filter_new_with_empty_input_returns_empty(tmp_path: Path):
    seen = SeenOffers(tmp_path / "seen_offers.db")

    assert seen.filter_new([]) == []
