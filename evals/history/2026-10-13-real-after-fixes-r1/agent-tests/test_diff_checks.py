import pytest
from playwright.sync_api import expect

@pytest.mark.diff_check
def test_sign_in_button_name(page, base_url):
    page.goto(base_url + "index.html")
    sign_in_button = page.get_by_role("button", name="Sign in")
    expect(sign_in_button).to_be_visible()

@pytest.mark.diff_check
def test_dashboard_upcoming_appointments_heading(signed_in):
    heading = signed_in.get_by_role("heading", name="Upcoming appointments")
    expect(heading).to_be_visible()

@pytest.mark.diff_check
def test_lab_results_frame_heading(signed_in):
    frame = signed_in.frame_locator("#lab-results-frame")
    heading = frame.get_by_role("heading", name="Lab results")
    expect(heading).to_be_visible()
