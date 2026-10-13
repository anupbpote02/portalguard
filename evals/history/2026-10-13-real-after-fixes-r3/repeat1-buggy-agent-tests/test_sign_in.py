import pytest
from playwright.sync_api import expect

@pytest.mark.journey("sign_in")
def test_sign_in(page, base_url, patient):
    page.goto(base_url + "index.html")
    expect(page.get_by_role("heading", name="Sign in")).to_be_visible()
    email_input = page.get_by_label("Email")
    password_input = page.get_by_label("Password")
    sign_in_button = page.get_by_role("button", name="Sign in")
    email_input.fill(patient["email"])
    password_input.fill(patient["password"])
    sign_in_button.click()
    expect(page).to_have_url(base_url + "dashboard.html")
    expect(page.get_by_role("heading", name=f"Welcome, {patient['name']}")).to_be_visible()
