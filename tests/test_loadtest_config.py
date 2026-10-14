"""Load-test users must cover every tenant, skip clinicians, and alternate tenants to spread the per-hospital limit."""
from loadtest.config import TENANTS, USER_IDS


def test_load_users_cover_every_tenant_without_clinicians():
    assert {user.split("-")[0] for user in USER_IDS} == set(TENANTS)
    assert not any(user.endswith("-clinician") for user in USER_IDS)


def test_consecutive_load_users_are_in_different_tenants():
    assert all(a.split("-")[0] != b.split("-")[0] for a, b in zip(USER_IDS, USER_IDS[1:]))
