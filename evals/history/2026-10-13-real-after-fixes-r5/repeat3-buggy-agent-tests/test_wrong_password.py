import pytest
from playwright.sync_api import expect

def test_wrong_password(page, base_url, patient):
    page.goto(base_url + "index.html")
    email_input = page.get_by_label("Email")
    password_input = page.get_by_label("Password")
    sign_in_button = page.get_by_role("button", name="Sign in")

    email_input.fill(patient["email"])
    password_input.fill("wrongpassword")
    sign_in_button.click()

    expect(page).to_have_url(base_url + "index.html")
    alert = page.get_by_role("alert")
    expect(alert).to_be_visible()
    # The baseline error message is "Incorrect email or password. Please try again."
    expect(alert).to_have_text("Incorrect email or password. Please try again.")
    expect(sign_in_button).to_be_visible()
