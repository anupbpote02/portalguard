import pytest
from playwright.sync_api import expect

@pytest.mark.sign_in
def test_sign_in(page, base_url, patient):
    page.goto(base_url + "index.html")
    # The sign-in page has no label or placeholder for email, use input[name=email]
    email_input = page.locator("input[name=email]")
    email_input.fill(patient["email"])
    password_input = page.locator("input[name=password]")
    password_input.fill(patient["password"])
    page.get_by_role("button", name="Sign in").click()
    expect(page).to_have_url(base_url + "dashboard.html")
    welcome = page.get_by_role("heading", name=f"Welcome, {patient['name']}")
    expect(welcome).to_be_visible()
