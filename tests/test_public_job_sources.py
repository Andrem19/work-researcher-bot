from work_researcher.providers.civil_service import parse_jobs as parse_civil_service
from work_researcher.providers.govuk_workhub import parse_reader_markdown


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
