import pytest
from playwright.sync_api import expect

@pytest.mark.lab_results
def test_lab_results(signed_in, patient):
    frame = signed_in.frame_locator("#lab-results-frame")
    heading = frame.get_by_role("heading", name="Lab results")
    expect(heading).to_be_visible()
    download_button = frame.get_by_role("button", name="Download PDF")
    expect(download_button).to_be_visible()
