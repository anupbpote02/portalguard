import pytest
from playwright.sync_api import expect

def test_download_pdf(signed_in, patient):
    page = signed_in
    frame = page.frame_locator("#lab-results-frame")
    with page.expect_download() as download_info:
        frame.get_by_role("button", name="Download PDF").click()
    download = download_info.value
    expected_filename = f"lab-results-{patient['mrn']}.pdf"
    assert download.suggested_filename == expected_filename
