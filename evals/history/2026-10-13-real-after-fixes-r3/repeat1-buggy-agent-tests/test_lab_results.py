import pytest
from playwright.sync_api import expect

@pytest.mark.journey("lab_results")
def test_lab_results(page, signed_in, patient):
    frame = page.frame_locator("#lab-results-frame")
    expect(frame.get_by_role("heading", name="Lab results")).to_be_visible()
    download_button = frame.get_by_role("button", name="Download PDF")
    expect(download_button).to_be_visible()
