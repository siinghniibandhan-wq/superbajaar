from app.api.customer_auth import _link_verified_legacy_loyalty_account


class Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class VerifiedLegacyLoyaltyConnection:
    def __init__(self, *, verified=True, existing_link=None):
        self.verified = verified
        self.existing_link = existing_link
        self.inserted = None

    def execute(self, query, params=()):
        if "FROM identity_profiles profile" in query:
            return Result({"party_id": 91} if self.verified else None)
        if "FROM loyalty_accounts" in query:
            assert params == ("buyer@example.com",)
            return Result({"id": 17})
        if "FROM identity_loyalty_accounts" in query:
            return Result(self.existing_link)
        if "INSERT INTO identity_loyalty_accounts" in query:
            self.inserted = params
            return Result({"id": 1})
        raise AssertionError(f"Unexpected SQL: {query}")


def test_verified_customer_contact_links_matching_legacy_loyalty_card():
    conn = VerifiedLegacyLoyaltyConnection()

    linked = _link_verified_legacy_loyalty_account(
        conn, customer_id=42, customer_email="Buyer@Example.com"
    )

    assert linked is True
    assert conn.inserted == (91, 17)


def test_unverified_customer_contact_does_not_link_legacy_card():
    conn = VerifiedLegacyLoyaltyConnection(verified=False)

    linked = _link_verified_legacy_loyalty_account(
        conn, customer_id=42, customer_email="buyer@example.com"
    )

    assert linked is False
    assert conn.inserted is None


def test_legacy_loyalty_card_already_linked_to_another_party_is_not_reassigned_or_block_login():
    conn = VerifiedLegacyLoyaltyConnection(existing_link={"party_id": 92})

    linked = _link_verified_legacy_loyalty_account(
        conn, customer_id=42, customer_email="buyer@example.com"
    )

    assert linked is False
    assert conn.inserted is None
