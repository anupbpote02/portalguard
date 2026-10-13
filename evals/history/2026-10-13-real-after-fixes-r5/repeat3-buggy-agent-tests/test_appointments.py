import pytest
from playwright.sync_api import expect

def test_appointments(signed_in, patient):
    page = signed_in
    expect(page.get_by_role("heading", name="Upcoming appointments")).to_be_visible()
    appointments = page.get_by_role("listitem")
    expect(appointments).to_have_count(len(patient["appointments"]))
    for i, appointment in enumerate(patient["appointments"]):
        expect(appointments.nth(i)).to_have_text(appointment)
