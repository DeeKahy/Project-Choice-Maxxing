"""Unit tests for the voting algorithms.

These are written against the public ``calculate_all_results`` entry point
plus the individual methods, with edge cases that previously crashed:

  * empty votes
  * single voter
  * single option
  * tied scores
  * duplicate option names
"""
import pytest

from algorithms import (
    borda_count,
    calculate_all_results,
    kemeny_young,
    parse_votes,
    schulze_method,
    score_voting,
    star_voting,
)


def _options(*names):
    return [{"id": i + 1, "name": n, "description": ""} for i, n in enumerate(names)]


def _vote(username, **scores_by_id):
    row = {"username": username, "submitted_at": "2026-01-01T00:00:00"}
    for k, v in scores_by_id.items():
        row[k] = str(v)
    return row


def test_calculate_all_results_with_no_votes_returns_empty():
    assert calculate_all_results([], _options("A", "B"), 5) == {}


def test_calculate_all_results_with_no_options_returns_empty():
    assert calculate_all_results([_vote("u", option_1=3)], [], 5) == {}


def test_score_voting_basic():
    options = _options("A", "B", "C")
    votes = [
        _vote("u1", option_1=5, option_2=3, option_3=0),
        _vote("u2", option_1=4, option_2=4, option_3=1),
    ]
    parsed = parse_votes(votes, options)
    result = score_voting(parsed, ["A", "B", "C"])
    assert result[0] == ("A", 9)
    assert result[1] == ("B", 7)
    assert result[2] == ("C", 1)


def test_borda_count_runs_on_tied_scores():
    """All-equal ballots should produce a result, not an exception."""
    options = _options("A", "B", "C")
    votes = [_vote("u1", option_1=3, option_2=3, option_3=3)]
    parsed = parse_votes(votes, options)
    out = borda_count(parsed, ["A", "B", "C"])
    assert len(out) == 3


def test_star_voting_with_single_option():
    """STAR's loop does len(options)-1 iterations and indexes options[1].
    With a single option that's a guaranteed IndexError."""
    options = _options("Only")
    votes = [_vote("u1", option_1=5)]
    parsed = parse_votes(votes, options)
    try:
        result = star_voting(parsed, ["Only"])
    except IndexError as e:
        pytest.fail(
            f"star_voting crashes when there is only one option (IndexError: {e}). "
            "Algorithm should short-circuit when len(options) < 2."
        )
    assert isinstance(result, list)


def test_schulze_with_single_option_returns_one_item():
    options = _options("Only")
    votes = [_vote("u1", option_1=5)]
    parsed = parse_votes(votes, options)
    result = schulze_method(parsed, ["Only"])
    assert len(result) == 1


def test_kemeny_young_runs_on_small_input():
    options = _options("A", "B", "C")
    votes = [
        _vote("u1", option_1=5, option_2=2, option_3=0),
        _vote("u2", option_1=4, option_2=3, option_3=1),
    ]
    parsed = parse_votes(votes, options)
    result = kemeny_young(parsed, ["A", "B", "C"])
    assert len(result) == 3
    # The top-ranked option should be A given both voters prefer it.
    assert result[0][0] == "A"


def test_parse_votes_crashes_on_non_numeric_score():
    """Documents the parse_votes contract — non-numeric strings raise.
    The fix belongs in the route layer (validate before calling)."""
    options = _options("A")
    votes = [{"username": "u", "submitted_at": "x", "option_1": "abc"}]
    with pytest.raises(ValueError):
        parse_votes(votes, options)


def test_parse_votes_crashes_on_empty_string_score():
    """Empty string in a CSV cell will hit `int('')` and crash."""
    options = _options("A")
    votes = [{"username": "u", "submitted_at": "x", "option_1": ""}]
    with pytest.raises(ValueError):
        parse_votes(votes, options)


def test_duplicate_option_names_known_limitation():
    """Two options named the same collapse in score_voting because totals
    is keyed by name. Documenting current behaviour — once fixed (e.g. by
    keying on id), update this test."""
    options = _options("Same", "Same")
    votes = [_vote("u", option_1=5, option_2=3)]
    parsed = parse_votes(votes, options)
    result = score_voting(parsed, ["Same", "Same"])
    # Both names dedupe to one bucket — the second score (3) overwrites the
    # first score (5) inside parse_votes' dict, then the totals dict has one
    # key that gets summed. This is buggy but deterministic; pin it.
    totals = dict(result)
    assert "Same" in totals
