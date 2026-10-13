import pytest
from playwright.sync_api import Page

# Test sign in page UI and functionality

def test_sign_in_page_ui(page: Page, base_url: str):
    page.goto(base_url)
    # Check heading
    sign_in_heading = page.get_by_role("heading", name="Sign in")
    assert sign_in_heading.is_visible()
    # Check sign in button has accessible name
    sign_in_button = page.get_by_role("button", name="Sign in")
    assert sign_in_button.is_visible()


def test_sign_in_functionality(page: Page, base_url: str, patient: dict):
    page.goto(base_url)
    page.get_by_label("Email").fill(patient["email"])
    page.get_by_label("Password").fill(patient["password"])
    page.get_by_role("button", name="Sign in").click()
    # After sign in, dashboard heading with patient name should be visible
    dashboard_heading = page.get_by_role("heading", name=f"Welcome, {patient['name']}")
    assert dashboard_heading.is_visible()
