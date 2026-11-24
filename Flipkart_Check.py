"""
Flipkart automation with Selenium.

The whole flow below is repeated again and again. Each run starts
RUN_INTERVAL_SECONDS (30) after the previous run ends. Press Ctrl+C to stop.
Every step is saved as one row in flipkart_history.csv (next to this script):
timestamp, run, page_name, step, status (SUCCESS / FAILED / SKIPPED), details.
A step is SKIPPED when an earlier step in the same run failed.

Note: the login steps need you at the terminal in every run, because Flipkart
sends a new OTP by SMS and the script waits for you to type it.

Flow:
  1. Open Flipkart and click "Mobiles"
  2. Click the Apple product, then the device image (opens Device Details page)
  3. Select the colour and storage if available, then click Buy Now
  4. Enter the phone number and click Continue
  5. Ask for the OTP in the terminal, enter it in the 6 boxes, click the button
  6. Check the image after login, then open the account dropdown and click Logout

Rule used for EVERY element:
  - wait up to 10 seconds for the element to be visible
  - if it is not found, scroll through the whole page looking for it
  - if it is still not found, print "element not found" and stop
  - once found, click it and wait 6 seconds before going to the next element

Elements that are only CHECKED (OTP page, OTP box, image after login, account
element in the header) are not clicked, because clicking them could change the
page. They are still waited for 10 seconds, scrolled for, and followed by a
6 second wait.

Install:  pip install selenium
(Selenium 4.6+ downloads the Chrome driver automatically.)
"""

import csv
import io
import os
import sys
import time
from contextlib import redirect_stdout
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# ----------------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------------
URL = "https://www.flipkart.com/"
PHONE_NUMBER = "7020996734"

WAIT_SECONDS = 10        # how long to wait for an element before scrolling
AFTER_CLICK_WAIT = 6     # pause after every click / check, before the next element
OTP_BOX_PAUSE = 0.5      # short pause between the 6 OTP digit boxes
MAX_SCROLLS = 60         # maximum scroll steps when looking through the page
SCROLL_PAUSE = 2.0       # pause after each scroll step (slow, so you can watch it)
SCROLL_STEP = 0.4        # how far each scroll step goes (0.4 = 40% of the screen height)
SMOOTH_SCROLL_TIME = 1.5 # time given to a smooth scroll to finish before continuing

RUN_INTERVAL_SECONDS = 30  # wait between the END of one run and the START of the next
MAX_RUNS = 0               # 0 = repeat until you press Ctrl+C
CSV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flipkart_history.csv")

# ----------------------------------------------------------------------------
# XPaths
# ----------------------------------------------------------------------------
# Home page: "Mobiles" label in the top category bar (second XPath is a fallback)
MOBILE_XPATHS = [
    '//*[@id="container"]/div/div[1]/div/div/div/div/div/div/div/div/div/div[1]'
    '/div/div/div[3]/div/div/div/div/div/div/div/div[3]/div/div/div/a/div/div/h1',
    '//a[.//*[normalize-space(text())="Mobiles"]]',
]

# Apple Products page: Apple product (picture + name)
APPLE_XPATH = (
    '//*[@id="slot-list-container"]/div/div[3]/div/div/div/div/div/div/div/div/div'
    '/div/div/div/div/div/div/div[1]/div[1]/div/div/div/div/a/div'
)

# Apple Products page: device image (opens Device Details page)
DEVICE_IMG_XPATH = (
    '/html/body/div[1]/div/div[1]/div/div/div/div/div/div/div/div/div/div[2]/div'
    '/div[7]/div/div/div/div/div/div/div/div/div/div/div[1]/div/div/div/a/div/picture/img'
)

# Device Details page: colour, storage, Buy Now
COLOUR_XPATH = (
    '/html/body/div[1]/div/div[1]/div/div/div/div/div/div/div/div/div/div/div[2]/div'
    '/div[2]/div/div/div/div[1]/div/div[2]/div/div[2]/div/div/div/div/div/div/div/div[2]'
    '/div/div/div/div[2]/div[2]/div/div/div/a/div/div[2]'
)
STORAGE_XPATH = (
    '/html/body/div[1]/div/div[1]/div/div/div/div/div/div/div/div/div/div/div[2]/div'
    '/div[2]/div/div/div/div[1]/div/div[2]/div/div[3]/div/div/div/div/div/div/div/div[2]'
    '/div/div[1]/div/div[2]/div[2]/div/div/div/a/div[5]'
)
BUY_NOW_XPATH = (
    '//*[@id="slot-list-container"]/div/div[2]/div/div/div/div[1]/div/div[2]/div/div[16]'
    '/div/div/div/div/div/div/div/div/div'
)

# Login box: phone number input and Continue button
PHONE_INPUT_XPATH = '/html/body/div[1]/div/div[4]/div/main/div/div/div[1]/section/div[3]/input'
CONTINUE_BTN_XPATH = '/html/body/div[1]/div/div[4]/div/main/div/div/div[3]/div/button'

# OTP page: page marker, box that holds the 6 inputs, one input per digit, button
OTP_PAGE_XPATH = '/html/body/div[1]/div/div[4]/div/main/div/div/div[1]/div/div[1]'
OTP_CONTAINER_XPATH = '/html/body/div[1]/div/div[4]/div/main/div/div/div[1]/div/div[2]'
OTP_BOX_XPATHS = [
    f'/html/body/div[1]/div/div[4]/div/main/div/div/div[1]/div/div[2]/div[{i}]/div/div/input'
    for i in range(1, 7)
]
OTP_VERIFY_BTN_XPATH = '/html/body/div[1]/div/div[4]/div/main/div/div/div[2]/div/button'

# Page after login: image to check
AFTER_LOGIN_IMG_XPATH = (
    '/html/body/div[1]/div/div[1]/div/div/div/div/div/div/div/div/div/div[2]/div/div[1]'
    '/div/div/div/div/div/div[1]/div/div[1]/div/div/div/div/div/div/img'
)

# Header: account element, dropdown arrow, Logout item
HEADER_ACCOUNT_XPATH = (
    '/html/body/div[1]/div/div[1]/div/div/div/div/div/div/div/div/div/div[1]/div/div'
    '/header/div[3]/div[2]/div/div/div/div/a'
)
HEADER_ARROW_XPATH = (
    '/html/body/div[1]/div/div[1]/div/div/div/div/div/div/div/div/div/div[1]/div/div'
    '/header/div[3]/div[3]/div/div/div/div/img'
)
LOGOUT_BTN_XPATH = (
    '/html/body/div[1]/div/div[1]/div/div/div/div/div[1]/div/div/div/div/div[1]/div/div'
    '/header/div[3]/div[2]/div/div/div/ul/a[11]/li/div/div/div'
)


# ----------------------------------------------------------------------------
# Core helpers (used by every step)
# ----------------------------------------------------------------------------
def as_list(xpaths):
    """Accept one XPath or a list of XPaths."""
    return [xpaths] if isinstance(xpaths, str) else list(xpaths)


def first_visible(driver, xpaths):
    """First displayed element matching any XPath, else False."""
    for xpath in xpaths:
        for element in driver.find_elements(By.XPATH, xpath):
            try:
                if element.is_displayed():
                    return element
            except StaleElementReferenceException:
                continue
    return False


def first_present(driver, xpaths):
    """First element that exists in the page (visible or not), else None."""
    for xpath in xpaths:
        found = driver.find_elements(By.XPATH, xpath)
        if found:
            return found[0]
    return None


def center_on_screen(driver, element):
    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", element
    )
    time.sleep(SMOOTH_SCROLL_TIME)  # let the smooth scroll finish so you can see it


def scroll_to_find(driver, xpaths):
    """Scroll slowly through the whole page, top to bottom, until an XPath element exists."""
    driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'});")
    time.sleep(SMOOTH_SCROLL_TIME)
    last_height = -1
    for _ in range(MAX_SCROLLS):
        element = first_present(driver, xpaths)
        if element is not None:
            return element

        driver.execute_script(
            "window.scrollBy({top: window.innerHeight * arguments[0], behavior: 'smooth'});",
            SCROLL_STEP,
        )
        time.sleep(SCROLL_PAUSE)

        new_height = driver.execute_script("return document.body.scrollHeight")
        at_bottom = driver.execute_script(
            "return (window.innerHeight + window.scrollY) >= document.body.scrollHeight - 5;"
        )
        if at_bottom and new_height == last_height:
            break
        last_height = new_height

    return first_present(driver, xpaths)


def find_element(driver, xpaths, label):
    """Wait up to 10 seconds. If not found, scroll through the whole page.
    Returns a visible element, or None (after printing 'element not found')."""
    xpaths = as_list(xpaths)

    # 1) wait up to 10 seconds
    try:
        element = WebDriverWait(driver, WAIT_SECONDS).until(
            lambda d: first_visible(d, xpaths)
        )
        center_on_screen(driver, element)
        return element
    except TimeoutException:
        print(f"{label}: not visible after {WAIT_SECONDS}s, scrolling through the page...")

    # 2) scroll through the whole page
    element = scroll_to_find(driver, xpaths)
    if element is None:
        print(f"ERROR: element not found - {label}")
        return None

    center_on_screen(driver, element)
    try:
        WebDriverWait(driver, WAIT_SECONDS).until(EC.visibility_of(element))
    except (TimeoutException, StaleElementReferenceException):
        print(f"ERROR: element not found - {label} is on the page but not visible.")
        return None
    return element


def click_element(driver, element, label, wait_after=AFTER_CLICK_WAIT):
    """Click an element (JavaScript click if something covers it), then wait."""
    try:
        WebDriverWait(driver, WAIT_SECONDS).until(lambda d: element.is_enabled())
    except (TimeoutException, StaleElementReferenceException):
        print(f"ERROR: {label} is not clickable.")
        return False

    try:
        element.click()
    except (ElementClickInterceptedException, ElementNotInteractableException):
        driver.execute_script("arguments[0].click();", element)
    print(f"SUCCESS: clicked on {label}.")
    time.sleep(wait_after)
    return True


def find_and_click(driver, xpaths, label, wait_after=AFTER_CLICK_WAIT):
    """Find an element (10s wait + page scroll), click it, wait 6 seconds.
    Returns the element, or None."""
    element = find_element(driver, xpaths, label)
    if element is None:
        return None
    if not click_element(driver, element, label, wait_after):
        return None
    return element


def find_only(driver, xpaths, label):
    """Find an element (10s wait + page scroll) without clicking it, wait 6 seconds.
    Returns the element, or None."""
    element = find_element(driver, xpaths, label)
    if element is None:
        return None
    print(f"SUCCESS: {label} is visible.")
    time.sleep(AFTER_CLICK_WAIT)
    return element


# ----------------------------------------------------------------------------
# Steps
# ----------------------------------------------------------------------------
def close_login_popup(driver):
    """Flipkart sometimes shows a login popup on the home page. Close it if present."""
    try:
        close_btn = WebDriverWait(driver, 4).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'✕')]"))
        )
        close_btn.click()
    except (TimeoutException, NoSuchElementException):
        pass  # no popup, continue


def step_open_mobiles(driver):
    return find_and_click(driver, MOBILE_XPATHS, "Mobiles icon") is not None


def step_click_apple(driver):
    element = find_element(driver, APPLE_XPATH, "Apple product")
    if element is None:
        return False
    text = element.text.strip().replace("\n", " | ")
    images = element.find_elements(By.TAG_NAME, "img")
    print(f'SUCCESS: Apple product is visible. Text: "{text}" | Images found: {len(images)}')
    return click_element(driver, element, "the Apple product")


def step_click_device_image(driver):
    handles_before = set(driver.window_handles)
    url_before = driver.current_url

    if find_and_click(driver, DEVICE_IMG_XPATH, "the device image") is None:
        return False

    # Flipkart may open the product in a new tab. Switch to it if so.
    new_handles = set(driver.window_handles) - handles_before
    if new_handles:
        driver.switch_to.window(new_handles.pop())

    try:
        WebDriverWait(driver, WAIT_SECONDS).until(
            lambda d: d.current_url != url_before or len(d.window_handles) > len(handles_before)
        )
    except TimeoutException:
        print("ERROR: clicked, but the Device Details page did not open.")
        return False

    print(f"SUCCESS: Device Details page opened. Title: {driver.title}")
    return True


def is_option_available(driver, element):
    """Available = visible, enabled, and the link does not say out of stock."""
    if not (element.is_displayed() and element.is_enabled()):
        return False
    if element.get_attribute("aria-disabled") == "true":
        return False
    text = driver.execute_script(
        "var a = arguments[0].closest('a') || arguments[0];"
        "return (a.innerText || '') + ' ' + (a.className || '');",
        element,
    ).lower()
    return not any(word in text for word in ("out of stock", "unavailable", "sold out"))


def select_option(driver, xpath, label):
    """Find an option (colour / storage). Select it only if it is available."""
    element = find_element(driver, xpath, f"{label} option")
    if element is None:
        return False

    option_text = element.text.strip().replace("\n", " | ")
    if not is_option_available(driver, element):
        print(f'ERROR: {label} option "{option_text}" is NOT available.')
        return False

    if not click_element(driver, element, f'{label} option "{option_text}"'):
        return False
    print(f'SUCCESS: {label} option "{option_text}" is available and selected.')
    return True


def step_select_colour(driver):
    return select_option(driver, COLOUR_XPATH, "Colour")


def step_select_storage(driver):
    return select_option(driver, STORAGE_XPATH, "Storage")


def step_buy_now(driver):
    return find_and_click(driver, BUY_NOW_XPATH, "Buy Now") is not None


def step_enter_phone(driver):
    box = find_and_click(driver, PHONE_INPUT_XPATH, "the phone number box")
    if box is None:
        return False

    box.clear()
    box.send_keys(PHONE_NUMBER)

    typed = (box.get_attribute("value") or "").replace(" ", "")
    if typed != PHONE_NUMBER:
        print(f'ERROR: phone number was not entered correctly (box shows "{typed}").')
        return False

    print(f"SUCCESS: phone number {PHONE_NUMBER} entered in the login box.")
    return True


def step_click_continue(driver):
    return find_and_click(driver, CONTINUE_BTN_XPATH, "Continue") is not None


def read_otp_boxes(driver):
    """Digits currently shown in the 6 OTP boxes, joined into one string."""
    digits = []
    for xpath in OTP_BOX_XPATHS:
        found = driver.find_elements(By.XPATH, xpath)
        digits.append((found[0].get_attribute("value") or "") if found else "")
    return "".join(digits)


def step_enter_otp(driver):
    # 1) the OTP page must be visible
    if find_only(driver, OTP_PAGE_XPATH, "the OTP page") is None:
        return False

    # 2) the box that holds the 6 inputs must be visible
    container = find_element(driver, OTP_CONTAINER_XPATH, "the OTP input box")
    if container is None:
        return False

    # 3) ask for the OTP in the terminal (sent by SMS to your phone)
    otp = input("Enter the 6 digit OTP received on your phone: ").strip().replace(" ", "")
    if not (otp.isdigit() and len(otp) == 6):
        print("ERROR: the OTP must be exactly 6 digits.")
        return False

    # 4) click each of the 6 boxes and type one digit
    for number, (xpath, digit) in enumerate(zip(OTP_BOX_XPATHS, otp), start=1):
        box = find_and_click(
            driver, xpath, f"OTP box {number}", wait_after=OTP_BOX_PAUSE
        )
        if box is None:
            print("Trying the whole OTP box instead.")
            break
        box.clear()
        box.send_keys(digit)

    # 5) if the boxes do not show the right digits, type into the whole box
    if read_otp_boxes(driver) != otp:
        ActionChains(driver).click(container).send_keys(otp).perform()
        time.sleep(1)
        if read_otp_boxes(driver) != otp:
            print(f'ERROR: OTP was not entered correctly (boxes show "{read_otp_boxes(driver)}").')
            return False
    print("SUCCESS: OTP entered in all 6 boxes.")
    time.sleep(AFTER_CLICK_WAIT)

    # 6) the button that appears after the OTP is entered
    if find_and_click(driver, OTP_VERIFY_BTN_XPATH, "the button after the OTP") is None:
        return False

    # 7) the OTP page should be gone if the OTP was accepted
    try:
        WebDriverWait(driver, WAIT_SECONDS).until(
            EC.invisibility_of_element_located((By.XPATH, OTP_PAGE_XPATH))
        )
    except TimeoutException:
        print("WARNING: the OTP page is still visible. The OTP may be wrong or expired.")
        return False

    print("SUCCESS: OTP accepted.")
    return True


def step_check_after_login_image(driver):
    return find_only(driver, AFTER_LOGIN_IMG_XPATH, "the image after login") is not None


def step_logout(driver):
    driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'});")  # header is at the top
    time.sleep(SMOOTH_SCROLL_TIME)

    # 1) the account element in the header must be visible (checked, not clicked)
    account = find_only(driver, HEADER_ACCOUNT_XPATH, "the account element in the header")
    if account is None:
        return False

    arrow = wait.until(EC.element_to_be_clickable((
    By.XPATH,
    '//*[@id="container"]/div/div[1]/div/div/div/div/div[1]/div/div/div/div/div[1]/div/div/header/div[3]/div[2]/div/div/div/div/img'
     )))
    arrow.click()

# Click Logout by its visible text
    logout = wait.until(EC.element_to_be_clickable((
    By.XPATH,
    '//a[.//li[normalize-space()="Logout"] or normalize-space()="Logout"]'
    )))
    logout.click()

    # the Logout item should be gone after the click
    try:
        WebDriverWait(driver, WAIT_SECONDS).until(
            EC.invisibility_of_element_located((By.XPATH, LOGOUT_BTN_XPATH))
        )
    except TimeoutException:
        print("WARNING: the Logout button is still visible. The logout may not have worked.")
        return False

    print("SUCCESS: logged out.")
    return True


# (page name, step name, function). The page name is what goes into the CSV.
# The 7 pages: Dashboard, Mobiles, Apple products, Details, Login,
# Otp confirmation, Logout.
STEPS = [
    ("Dashboard page", "Click Mobiles", step_open_mobiles),
    ("Mobiles page", "Click the Apple product", step_click_apple),
    ("Apple products page", "Click the device image", step_click_device_image),
    ("Details page", "Select the colour", step_select_colour),
    ("Details page", "Select the storage", step_select_storage),
    ("Details page", "Click Buy Now", step_buy_now),
    ("Login page", "Enter the phone number", step_enter_phone),
    ("Login page", "Click Continue", step_click_continue),
    ("Otp confirmation page", "Enter the OTP", step_enter_otp),
    ("Logout page", "Check the image after login", step_check_after_login_image),
    ("Logout page", "Log out", step_logout),
]

CSV_COLUMNS = ["timestamp", "run", "page_name", "step", "status", "details"]


# ----------------------------------------------------------------------------
# CSV history
# ----------------------------------------------------------------------------
def log_row(run_number, page, step, status, details):
    """Append one row to the CSV history file (the header is written once)."""
    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        run_number,
        page,
        step,
        status,
        details,
    ]
    for attempt in range(5):
        try:
            new_file = not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0
            with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if new_file:
                    writer.writerow(CSV_COLUMNS)
                writer.writerow(row)
            return
        except PermissionError:
            # usually the CSV is open in Excel. Wait a little and try again.
            print("WARNING: cannot write to the CSV file. Close it if it is open in Excel.")
            time.sleep(2)
    print(f"ERROR: could not save this row to the CSV: {row}")


class Tee(io.TextIOBase):
    """Print to the console and keep a copy, so the message can be saved in the CSV."""

    def __init__(self, console):
        self.console = console
        self.copy = io.StringIO()

    def write(self, text):
        self.console.write(text)
        self.copy.write(text)
        return len(text)

    def flush(self):
        self.console.flush()


def step_details(text):
    """The message to store in the CSV: the last ERROR/WARNING line, else the last line."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith(("ERROR", "WARNING")):
            return line
    return lines[-1] if lines else ""


# ----------------------------------------------------------------------------
# One run and the repeat loop
# ----------------------------------------------------------------------------
def run_once(run_number):
    """One full pass through all steps with a fresh browser.
    Writes one CSV row per step. Returns True if every step succeeded."""
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")

    driver = None
    setup_error = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get(URL)
        close_login_popup(driver)
    except Exception as exc:
        setup_error = f"could not open Flipkart: {exc}"
        print(f"ERROR: {setup_error}")

    stopped = False
    try:
        for index, (page, name, step) in enumerate(STEPS):
            if stopped:
                log_row(run_number, page, name, "SKIPPED", "an earlier step failed")
                continue
            if setup_error:
                log_row(run_number, page, name, "FAILED", setup_error)
                stopped = True
                continue

            print(f"\n--- {name} ({page}) ---")
            tee = Tee(sys.stdout)
            try:
                with redirect_stdout(tee):
                    ok = step(driver)
            except Exception as exc:
                ok = False
                tee.write(f"ERROR: unexpected problem - {exc}\n")

            log_row(
                run_number, page, name,
                "SUCCESS" if ok else "FAILED",
                step_details(tee.copy.getvalue()),
            )
            if not ok:
                print(f"STOPPED at step: {name}")
                stopped = True
    finally:
        if driver is not None:
            driver.quit()

    return not stopped


def main():
    print(f"History is saved in: {CSV_FILE}")
    print(f"Each run starts {RUN_INTERVAL_SECONDS} seconds after the previous run ends.")
    print("Press Ctrl+C to stop.")

    run_number = 0
    try:
        while True:
            run_number += 1
            print(f"\n==================== RUN {run_number} "
                  f"({datetime.now():%Y-%m-%d %H:%M:%S}) ====================")
            ok = run_once(run_number)
            print(f"\nRUN {run_number}: {'ALL STEPS SUCCEEDED' if ok else 'FAILED'}")

            if MAX_RUNS and run_number >= MAX_RUNS:
                break
            print(f"Next run in {RUN_INTERVAL_SECONDS} seconds...")
            time.sleep(RUN_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nStopped with Ctrl+C.")

    print(f"Finished after {run_number} run(s). History: {CSV_FILE}")


if __name__ == "__main__":
    main()