from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import httpx

from work_researcher.providers.base import SearchQuery
from work_researcher.providers.civil_service import parse_jobs as parse_civil_service
from work_researcher.providers.govuk_workhub import parse_reader_markdown
from work_researcher.providers.reed import fetch as fetch_reed
from work_researcher.providers.reed import search_url as reed_search_url


def test_reed_search_honours_location_and_direct_employer_filter() -> None:
    query = SearchQuery({
        "query": "Data Engineer", "location": "Manchester",
        "direct_employers_only": True, "radius_miles": 40,
    })
    url = urlparse(reed_search_url(query))
    assert url.path == "/jobs/data-engineer-jobs-in-manchester"
    assert parse_qs(url.query)["direct"] == ["true"]
    assert parse_qs(url.query)["proximity"] == ["40"]
    query["location"] = "UK"
    query["direct_employers_only"] = False
    assert urlparse(reed_search_url(query)).path == "/jobs/data-engineer-jobs"
    assert "direct" not in parse_qs(urlparse(reed_search_url(query)).query)


async def test_reed_follows_pagination_and_deduplicates_cards() -> None:
    def card(job_id: int) -> str:
        return (
            '<article data-qa="job-card">'
            f'<a data-qa="job-card-title" href="/jobs/data-engineer/{job_id}">Data Engineer</a>'
            '<span data-qa="job-posted-by">Today by Acme</span></article>'
        )

    requests = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params.get("pageno") == "2":
            body = card(1) + card(2)
        else:
            body = card(1) + '<a aria-label="Next page" href="?pageno=2">Next</a>'
        return httpx.Response(200, text=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    with patch("work_researcher.providers.reed.html_client", return_value=client):
        cards = await fetch_reed(SearchQuery({"query": "Data Engineer", "limit": 2}), {})
    assert len(requests) == 2
    assert len(cards) == 2
    assert cards[0].url != cards[1].url


def test_parse_govuk_reader_results() -> None:
    markdown = """## [Associate Data Engineer](https://www.jobs.service.gov.uk/jobs/6a8c6af6cc6b9c0465071b6d)
Example Employer - Manchester, United Kingdom

£28,000 to £32,000 a year

Hybrid Permanent Full time

Entry-level SQL and Python role.

* * *
"""
    cards = parse_reader_markdown(markdown)
    assert len(cards) == 1
    assert cards[0].source == "findajob"
    assert cards[0].company == "Example Employer"
    assert cards[0].salary_min == 28000
    assert cards[0].work_from_home is True


def test_parse_govuk_result_without_salary_or_location() -> None:
    markdown = """## [Junior Data Analyst](https://www.jobs.service.gov.uk/jobs/6a73991edd77f4c891a1974a)
Staffline

On-site Temporary Full time

Junior analytics vacancy description.

* * *
"""
    card = parse_reader_markdown(markdown)[0]
    assert card.company == "Staffline"
    assert card.location_text is None
    assert card.salary_raw is None
    assert card.contract_type == "On-site Temporary Full time"


def test_parse_civil_service_official_feed() -> None:
    html = """<article class="job">
      <h4 class="job__title"><a href="https://www.civilservicejobs.service.gov.uk/csr/jobs.cgi?vxsys=4&amp;vxvac=473210">Associate Performance Analyst</a></h4>
      <div class="job__summary">
        <p class="job__customer-name">DWP</p><p class="job__city-name">Manchester</p>
        <p class="job__salary">£31,000</p><span class="job__closing-date">Closes: 10 September 2026</span>
        <li class="job__roletype">Digital</li><li class="job__roletype">Analysis</li>
      </div>
    </article>"""
    cards = parse_civil_service(html)
    assert len(cards) == 1
    assert cards[0].source == "civil_service"
    assert cards[0].source_job_id == "473210"
    assert cards[0].company == "DWP"
    assert cards[0].salary_min == 31000
