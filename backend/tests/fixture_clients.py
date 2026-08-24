"""Fixture API clients for connector tests: same shapes the real HTTP clients
return, with `updated_after`/`created_after` filtering so incremental-sync
semantics are exercised for real."""


class FixtureHubSpotClient:
    def __init__(self, companies=None, contacts=None, deals=None):
        self.companies = companies or []
        self.contacts = contacts or []
        self.deals = deals or []

    @staticmethod
    def _filter(objs, updated_after):
        if updated_after is None:
            return list(objs)
        return [o for o in objs if o.get("updatedAt", "") > updated_after]

    def list_companies(self, updated_after=None):
        return self._filter(self.companies, updated_after)

    def list_contacts(self, updated_after=None):
        return self._filter(self.contacts, updated_after)

    def list_deals(self, updated_after=None):
        return self._filter(self.deals, updated_after)


class FixtureSalesforceClient:
    """SOQL-shaped records; incremental filters on LastModifiedDate /
    CreatedDate to exercise cursor semantics like the real client."""

    def __init__(self, accounts=None, contacts=None, opportunities=None, history=None):
        self.accounts = accounts or []
        self.contacts = contacts or []
        self.opportunities = opportunities or []
        self.history = history or []

    @staticmethod
    def _filter(objs, cursor, field):
        if cursor is None:
            return list(objs)
        return [o for o in objs if o.get(field, "") > cursor]

    def query_accounts(self, updated_after=None):
        return self._filter(self.accounts, updated_after, "LastModifiedDate")

    def query_contacts(self, updated_after=None):
        return self._filter(self.contacts, updated_after, "LastModifiedDate")

    def query_opportunities(self, updated_after=None):
        return self._filter(self.opportunities, updated_after, "LastModifiedDate")

    def query_opportunity_history(self, updated_after=None):
        return self._filter(self.history, updated_after, "CreatedDate")


class FixtureStripeClient:
    def __init__(self, customers=None, invoices=None):
        self.customers = customers or []
        self.invoices = invoices or []

    @staticmethod
    def _filter(objs, created_after):
        if created_after is None:
            return list(objs)
        return [o for o in objs if str(o.get("created", "")) > created_after]

    def list_customers(self, created_after=None):
        return self._filter(self.customers, created_after)

    def list_invoices(self, created_after=None):
        return self._filter(self.invoices, created_after)
