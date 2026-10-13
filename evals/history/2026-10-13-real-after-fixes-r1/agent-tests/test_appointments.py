import pytest
from playwright.sync_api import expect

@pytest.mark.appointments
def test_appointments(signed_in, patient):
    heading = signed_in.get_by_role("heading", name="Upcoming appointments")
    expect(heading).to_be_visible()
    for appointment in patient["appointments"]:
        appointment_text = signed_in.get_by_text(appointment)
        expect(appointment_text).to_be_visible()
