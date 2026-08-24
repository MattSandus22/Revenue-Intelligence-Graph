"""Connector factory: (source type, decrypted credentials, config) → Connector.

Each builder documents the exact secret fields it needs — the same contract
the setup wizard's consent screen shows the admin (docs/11 §11.0). Builders
are a plain registry so tests can substitute fixture-backed connectors.
"""

from typing import Callable

from .base import Connector
from .hubspot import HttpHubSpotClient, HubSpotConnector
from .salesforce import HttpSalesforceClient, SalesforceConnector
from .stripe import HttpStripeClient, StripeConnector
from .zendesk import HttpZendeskClient, ZendeskConnector


class CredentialError(Exception):
    pass


def _require(credentials: dict, *fields: str) -> None:
    missing = [f for f in fields if not credentials.get(f)]
    if missing:
        raise CredentialError(f"missing credential fields: {missing}")


def _build_hubspot(credentials: dict, config: dict) -> Connector:
    return HubSpotConnector(HttpHubSpotClient(credentials["access_token"]),
                            mapping=config.get("mapping"))


def _build_stripe(credentials: dict, config: dict) -> Connector:
    return StripeConnector(HttpStripeClient(credentials["api_key"]))


def _build_zendesk(credentials: dict, config: dict) -> Connector:
    return ZendeskConnector(HttpZendeskClient(
        credentials["subdomain"], credentials["email"], credentials["api_token"]))


def _build_salesforce(credentials: dict, config: dict) -> Connector:
    return SalesforceConnector(
        HttpSalesforceClient(credentials["instance_url"], credentials["access_token"]),
        mapping=config.get("mapping"))


# Single source of truth for which fields each connector needs; the builders
# and the API validation both read it, so the two cannot drift.
REQUIRED_FIELDS: dict[str, list[str]] = {
    "hubspot": ["access_token"],
    "stripe": ["api_key"],
    "zendesk": ["subdomain", "email", "api_token"],
    "salesforce": ["instance_url", "access_token"],
}

BUILDERS: dict[str, Callable[[dict, dict], Connector]] = {
    "hubspot": _build_hubspot,
    "stripe": _build_stripe,
    "zendesk": _build_zendesk,
    "salesforce": _build_salesforce,
}

# Names that must never appear in plaintext data_source.config — they belong
# in the encrypted credential store.
SECRET_FIELD_NAMES: set[str] = (
    {name for fields in REQUIRED_FIELDS.values() for name in fields}
    | {"token", "secret", "password", "client_secret", "refresh_token"}
)


def build_connector(source_type: str, credentials: dict, config: dict | None = None) -> Connector:
    builder = BUILDERS.get(source_type)
    if builder is None:
        raise CredentialError(f"unknown connector type '{source_type}';"
                              f" supported: {sorted(BUILDERS)}")
    _require(credentials, *REQUIRED_FIELDS.get(source_type, []))
    return builder(credentials, config or {})
