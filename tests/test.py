import re
from playwright.sync_api import Page, expect

def test_has_title(page: Page):
    page.goto("https://practicetestautomation.com/practice-test-login/")

    # Expect a title "to contain" a substring.
    expect(page).to_have_title("Test Login | Practice Test Automation")
    page.fill("#username", "student")
    page.fill("#password", "Password123")
    page.click("#submit")

    # Expect the logged-in page title.
    expect(page).to_have_title("Logged In Successfully | Practice Test Automation")
