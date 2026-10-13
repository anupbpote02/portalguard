import pytest
from playwright.sync_api import expect

@pytest.mark.wrong_password
def test_wrong_password(page, base_url, patient):
    page.goto(base_url + "index.html")
    # The sign-in page has no label or placeholder for email, use input[name=email]
    email_input = page.locator("input[name=email]")
    email_input.fill(patient["email"])
    password_input = page.locator("input[name=password]")
    password_input.fill("wrongpassword")
    page.get_by_role("button", name="Sign in").click()
    error_message = page.get_by_role("alert")
    expect(error_message).to_be_visible()
    expect(error_message).to_have_text("Invalid email or password.")
