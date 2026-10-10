from unittest.mock import Mock, patch

from aelyn_career.source_adapters import (
    WorkdayAdapter,
    _parse_workday_sites,
    _strip_html,
)


def test_parse_workday_sites_splits_tenant_version_and_site():
    raw = "astrazeneca:wd3:Careers,ipsen:wd103:Ipsen_Careers"
    assert _parse_workday_sites(raw) == [
        ("astrazeneca", "wd3", "Careers"),
        ("ipsen", "wd103", "Ipsen_Careers"),
    ]


def test_parse_workday_sites_ignores_malformed_entries():
    assert _parse_workday_sites("missing-parts,astrazeneca:wd3:Careers,::") == [
        ("astrazeneca", "wd3", "Careers"),
    ]


def test_parse_workday_sites_returns_empty_list_for_blank_input():
    assert _parse_workday_sites("") == []


def test_strip_html_removes_tags_and_converts_breaks_to_newlines():
    html = "<p>Bonjour</p><ul><li>Un</li><li>Deux</li></ul>"
    assert _strip_html(html) == "Bonjour\nUn\nDeux"


def test_strip_html_returns_none_for_empty_input():
    assert _strip_html(None) is None
    assert _strip_html("") is None


def test_workday_adapter_returns_empty_list_without_configured_sites(monkeypatch):
    monkeypatch.delenv("WORKDAY_CAREERS_SITES", raising=False)
    assert WorkdayAdapter().search(keywords="stage") == []


def test_workday_adapter_returns_empty_list_without_keywords(monkeypatch):
    monkeypatch.setenv("WORKDAY_CAREERS_SITES", "astrazeneca:wd3:Careers")
    assert WorkdayAdapter().search(keywords=None) == []


def _fake_response(json_data, *, ok=True):
    response = Mock()
    response.json.return_value = json_data
    if ok:
        response.raise_for_status = Mock()
    else:
        response.raise_for_status = Mock(side_effect=RuntimeError("boom"))
    return response


def test_workday_adapter_normalizes_a_real_search_result(monkeypatch):
    monkeypatch.setenv("WORKDAY_CAREERS_SITES", "astrazeneca:wd3:Careers")
    search_response = _fake_response({
        "total": 1,
        "jobPostings": [{
            "title": "Stage Data Scientist",
            "externalPath": "/job/France---La-Defense/Stage_R-123",
            "timeType": "Internship",
            "locationsText": "France - La Defense",
            "postedOn": "Posted Yesterday",
        }],
    })
    description_html = "<p>Analyse de donnees</p><p>R et Python</p>"
    detail_response = _fake_response({
        "jobPostingInfo": {"jobDescription": description_html},
    })
    with (
        patch(
            "aelyn_career.source_adapters.requests.post", return_value=search_response
        ),
        patch(
            "aelyn_career.source_adapters.requests.get", return_value=detail_response
        ),
    ):
        results = WorkdayAdapter().search(keywords="stage", limit=5)

    assert len(results) == 1
    offer = results[0]
    assert offer["title"] == "Stage Data Scientist"
    assert offer["company"] == "astrazeneca"
    assert offer["location"] == "France - La Defense"
    assert offer["source"] == "workday"
    assert offer["url"] == (
        "https://astrazeneca.wd3.myworkdayjobs.com/Careers"
        "/job/France---La-Defense/Stage_R-123"
    )
    assert offer["description"] == "Analyse de donnees\nR et Python"


def test_workday_adapter_queries_every_configured_tenant(monkeypatch):
    monkeypatch.setenv(
        "WORKDAY_CAREERS_SITES", "astrazeneca:wd3:Careers,ipsen:wd103:Ipsen_Careers"
    )
    empty_response = _fake_response({"jobPostings": []})
    with patch(
        "aelyn_career.source_adapters.requests.post", return_value=empty_response
    ) as mock_post:
        WorkdayAdapter().search(keywords="stage", limit=5)

    called_urls = [call.args[0] for call in mock_post.call_args_list]
    astrazeneca_url = (
        "https://astrazeneca.wd3.myworkdayjobs.com/wday/cxs/astrazeneca/Careers/jobs"
    )
    ipsen_url = (
        "https://ipsen.wd103.myworkdayjobs.com/wday/cxs/ipsen/Ipsen_Careers/jobs"
    )
    assert astrazeneca_url in called_urls
    assert ipsen_url in called_urls


def test_workday_adapter_returns_empty_list_when_a_tenant_request_fails(monkeypatch):
    monkeypatch.setenv("WORKDAY_CAREERS_SITES", "astrazeneca:wd3:Careers")
    with patch(
        "aelyn_career.source_adapters.requests.post",
        side_effect=RuntimeError("network error"),
    ):
        assert WorkdayAdapter().search(keywords="stage") == []


def test_workday_adapter_keeps_the_posting_when_the_detail_fetch_fails(monkeypatch):
    """Un echec du GET de detail (description) ne doit jamais faire perdre
    l'offre entiere : mieux vaut une offre sans description qu'aucune
    offre, le titre/l'URL restent utiles."""
    monkeypatch.setenv("WORKDAY_CAREERS_SITES", "astrazeneca:wd3:Careers")
    search_response = _fake_response({
        "jobPostings": [{
            "title": "Stage Data Scientist",
            "externalPath": "/job/France/Stage_R-123",
            "locationsText": "France",
        }],
    })
    with (
        patch(
            "aelyn_career.source_adapters.requests.post", return_value=search_response
        ),
        patch(
            "aelyn_career.source_adapters.requests.get",
            side_effect=RuntimeError("timeout"),
        ),
    ):
        results = WorkdayAdapter().search(keywords="stage", limit=5)

    assert len(results) == 1
    assert results[0]["title"] == "Stage Data Scientist"
    assert results[0]["description"] is None
