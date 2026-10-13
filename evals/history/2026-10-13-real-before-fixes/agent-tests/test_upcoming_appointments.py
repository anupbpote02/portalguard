import pytest
from playwright.sync_api import Page

# Test upcoming appointments visible on dashboard

def test_upcoming_appointments_visible(signed_in: Page, patient: dict):
    # Check heading for upcoming appointments
    heading = signed_in.get_by_role("heading", name="Upcoming appointments")
    assert heading.is_visible()
    # Check at least one appointment is listed
    for appt in patient["appointments"]:
        assert signed_in.get_by_text(appt).is_visible()
