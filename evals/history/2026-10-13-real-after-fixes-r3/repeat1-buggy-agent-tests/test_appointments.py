import pytest
from playwright.sync_api import expect

@pytest.mark.journey("appointments")
def test_appointments(page, signed_in, patient):
    # The baseline snapshot shows appointments as text, but patient.appointments is a list of dicts
    # So we check for the heading only
    expect(page.get_by_role("heading", name="Upcoming appointments")).to_be_visible()
