import pytest
from playwright.sync_api import Page

# Test lab results frame UI and download

def test_lab_results_heading_and_button(signed_in: Page):
    frame = signed_in.frame_locator("#lab-results-frame")
    # Check heading "Lab results" is visible
    heading = frame.get_by_role("heading", name="Lab results")
    assert heading.is_visible()
    # Check download PDF button
    download_button = frame.get_by_role("button", name="Download PDF")
    assert download_button.is_visible()


def test_lab_results_download_pdf(signed_in: Page, patient: dict):
    frame = signed_in.frame_locator("#lab-results-frame")
    with signed_in.expect_download() as download_info:
        frame.get_by_role("button", name="Download PDF").click()
    download = download_info.value
    assert download.suggested_filename == f"lab-results-{patient['mrn']}.pdf"
