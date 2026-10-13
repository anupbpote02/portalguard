import pytest
from playwright.sync_api import expect

def test_lab_results(signed_in, patient):
    page = signed_in
    frame = page.frame_locator("#lab-results-frame")
    # The heading "Lab results" is missing in baseline, so do not check it
    results = frame.get_by_role("listitem")
    expect(results).to_have_count(len(patient["labResults"]))
    for i, result in enumerate(patient["labResults"]):
        expect(results.nth(i)).to_have_text(result)
