from ingestion.http_client import session


def test_fetchers_retry_transient_failures():
    retry = session.get_adapter("https://api.fda.gov").max_retries
    assert retry.connect >= 3
    assert retry.read >= 3
    assert {429, 503} <= set(retry.status_forcelist)
    assert 404 not in retry.status_forcelist
    assert set(retry.allowed_methods) == {"GET"}