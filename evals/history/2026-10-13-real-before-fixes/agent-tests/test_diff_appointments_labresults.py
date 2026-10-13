import pytest
from playwright.sync_api import Page

# Test for diff: missing upcoming appointments heading on dashboard

def test_missing_upcoming_appointments_heading(signed_in: Page):
    # The heading "Upcoming appointments" should be present
    heading = signed_in.get_by_role("heading", name="Upcoming appointments")
    assert heading.is_visible()

# Test for diff: missing lab results heading in iframe

def test_missing_lab_results_heading(signed_in: Page):
    frame = signed_in.frame_locator("#lab-results-frame")
    heading = frame.get_by_role("heading", name="Lab results")
    assert heading.is_visible()

# Test for diff: sign in button has no accessible name

def test_sign_in_button_accessible_name(page: Page, base_url: str):
    page.goto(base_url)
    button = page.get_by_role("button")
    # The button should have accessible name "Sign in"
    assert button.get_attribute("name") == "Sign in" or button.get_attribute("aria-label") == "Sign in" or button.text_content() == "Sign in"
