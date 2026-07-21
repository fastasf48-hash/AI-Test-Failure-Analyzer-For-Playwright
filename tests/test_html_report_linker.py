import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, ResultStatus
from app.database.repository import Repository
from app.reports.html_report_linker import link_html_report


@pytest.fixture()
def repo():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    try:
        yield Repository(session)
    finally:
        session.close()


def test_links_report_only_to_failed_results(repo):
    run = repo.create_test_run(execution_id="run-1")
    failed = repo.add_test_result(run_id=run.id, test_name="a", status=ResultStatus.FAILED)
    passed = repo.add_test_result(run_id=run.id, test_name="b", status=ResultStatus.PASSED)

    linked = link_html_report(repo, run.id, "reports/pytest-report.html")

    assert linked == 1
    assert repo.get_test_result(failed.id).html_report_path == "reports/pytest-report.html"
    assert repo.get_test_result(passed.id).html_report_path is None


def test_returns_zero_for_unknown_run(repo):
    assert link_html_report(repo, 9999, "reports/pytest-report.html") == 0


def test_returns_zero_when_run_has_no_failures(repo):
    run = repo.create_test_run(execution_id="run-2")
    repo.add_test_result(run_id=run.id, test_name="a", status=ResultStatus.PASSED)

    assert link_html_report(repo, run.id, "reports/pytest-report.html") == 0
