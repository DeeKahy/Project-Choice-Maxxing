"""Tests for the public vote/results routes.

These tests are written to *exercise the suspect crash paths* — duplicate
usernames, blank usernames, and non-numeric scores — so failures here are
the bug list in executable form.
"""
import pytest


def test_get_vote_page_renders(client, sample_poll):
    resp = client.get(f"/vote/{sample_poll}")
    assert resp.status_code == 200
    assert b"Submit Vote" in resp.data


def test_vote_unknown_poll_returns_404(client):
    resp = client.get("/vote/nope")
    assert resp.status_code == 404


def test_vote_happy_path(client, sample_poll, app_module):
    resp = client.post(
        f"/vote/{sample_poll}",
        data={
            "username": "alice",
            "score_1": "5",
            "score_2": "3",
            "score_3": "0",
        },
    )
    # Successful submission is a Post/Redirect/Get → results page.
    assert resp.status_code == 302
    assert f"/results/{sample_poll}" in resp.headers["Location"]
    votes = app_module.get_votes(sample_poll)
    assert len(votes) == 1
    assert votes[0]["username"] == "alice"


def test_vote_on_closed_poll_redirects_to_results(admin_client, client, sample_poll):
    admin_client.post(f"/admin/poll/{sample_poll}/toggle")  # close it
    resp = client.get(f"/vote/{sample_poll}")
    assert resp.status_code == 302
    assert f"/results/{sample_poll}" in resp.headers["Location"]


def test_blank_username_does_not_crash(client, sample_poll):
    """REGRESSION GUARD: app.py renders 'vote.html' on validation failure
    but the actual template is 'voting.html', so blank-username submissions
    currently raise TemplateNotFound. Once the bug is fixed this test should
    pass with a 200 + the error message."""
    resp = client.post(
        f"/vote/{sample_poll}",
        data={"username": "  ", "score_1": "0", "score_2": "0", "score_3": "0"},
    )
    assert resp.status_code == 200, (
        "Blank username crashed the vote route. "
        "Likely TemplateNotFound: app.py uses 'vote.html', file is 'voting.html'."
    )
    assert b"Username required" in resp.data


def test_duplicate_username_does_not_crash(client, sample_poll):
    """Same root cause as the blank-username case — second submission as the
    same user re-renders the wrong template name."""
    payload = {
        "username": "bob",
        "score_1": "1",
        "score_2": "2",
        "score_3": "3",
    }
    first = client.post(f"/vote/{sample_poll}", data=payload)
    assert first.status_code == 302  # successful vote redirects
    second = client.post(f"/vote/{sample_poll}", data=payload)
    assert second.status_code == 200, (
        "Duplicate username crashed the vote route. "
        "Likely TemplateNotFound: 'vote.html' vs 'voting.html'."
    )
    assert b"already voted" in second.data


def test_non_numeric_score_does_not_500(client, sample_poll):
    """parse_votes does int(score) with no validation. A POST with a
    non-numeric score should be rejected with a 4xx, never a 500."""
    resp = client.post(
        f"/vote/{sample_poll}",
        data={
            "username": "carol",
            "score_1": "not-a-number",
            "score_2": "0",
            "score_3": "0",
        },
    )
    assert resp.status_code < 500, (
        "Non-numeric score caused a server crash. "
        "Validate scores in vote() before persisting."
    )


def test_results_renders_with_no_votes(client, sample_poll):
    resp = client.get(f"/results/{sample_poll}")
    assert resp.status_code == 200


def test_results_renders_after_one_vote(client, sample_poll):
    client.post(
        f"/vote/{sample_poll}",
        data={"username": "dave", "score_1": "5", "score_2": "1", "score_3": "0"},
    )
    resp = client.get(f"/results/{sample_poll}")
    assert resp.status_code == 200
    assert b"Score Voting" in resp.data
    # The Borda section was previously mis-labelled "Schulze Method" — assert
    # the proper heading rendered exactly once (Schulze still has its own).
    assert b"Borda Count" in resp.data
    assert resp.data.count(b"Schulze Method") == 1


def test_results_renders_with_many_voters(client, sample_poll):
    for i in range(5):
        client.post(
            f"/vote/{sample_poll}",
            data={
                "username": f"voter{i}",
                "score_1": str(i % 6),
                "score_2": str((i + 1) % 6),
                "score_3": str((i + 2) % 6),
            },
        )
    resp = client.get(f"/results/{sample_poll}")
    assert resp.status_code == 200
