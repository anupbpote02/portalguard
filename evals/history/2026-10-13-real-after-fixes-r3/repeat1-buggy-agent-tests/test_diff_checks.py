import pytest
from playwright.sync_api import expect

@pytest.mark.journey("diff_check")
def test_sign_in_button_name(page, base_url):
    page.goto(base_url + "index.html")
    # Check that the sign in button has accessible name "Sign in"
    sign_in_button = page.get_by_role("button", name="Sign in")
    expect(sign_in_button).to_be_visible()

@pytest.mark.journey("diff_check")
def test_dashboard_upcoming_appointments_heading(page, signed_in):
    # Check that the dashboard has heading "Upcoming appointments"
    expect(page.get_by_role("heading", name="Upcoming appointments")).to_be_visible()

@pytest.mark.journey("diff_check")
def test_lab_results_frame_heading(page, signed_in):
    frame = page.frame_locator("#lab-results-frame")
    # Check that the lab results iframe has heading "Lab results"
    expect(frame.get_by_role("heading", name="Lab results")).to_be_visible()
