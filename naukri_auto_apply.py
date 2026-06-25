"""
Naukri Auto-Apply Bot
=====================
Automatically logs into Naukri.com, searches for jobs based on your
preferences, and applies to matching listings.

Credentials are read from environment variables (GitHub Secrets).
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, ElementClickInterceptedException
)
from webdriver_manager.chrome import ChromeDriverManager
import time
import logging
import json
import os
from datetime import datetime

# ─────────────────────────────────────────────
#  CONFIG — Credentials from environment variables
# ─────────────────────────────────────────────
CONFIG = {
    "email": os.environ.get("NAUKRI_EMAIL", ""),
    "password": os.environ.get("NAUKRI_PASSWORD", ""),

    "search_keywords": ["Java Developer", "Python Developer", "SQL Developer"],
    "location": "Hyderabad",
    "experience_min": 0,
    "experience_max": 1,

    "required_skills": ["java", "python", "sql", "mysql", "postgresql"],
    "exclude_keywords": ["senior", "lead", "manager", "architect", "10+", "8+", "5+"],

    "max_apply_per_search": 10,
    "action_delay": 2,
    "log_file": "applied_jobs.json",
}

# ─────────────────────────────────────────────
#  Logging setup
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("naukri_bot.log"),
    ],
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  Applied jobs tracker
# ─────────────────────────────────────────────
def load_applied(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

def save_applied(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ─────────────────────────────────────────────
#  Browser setup — Headless for GitHub Actions
# ─────────────────────────────────────────────
def create_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")           # headless for CI/CD
    options.add_argument("--no-sandbox")             # required for GitHub Actions
    options.add_argument("--disable-dev-shm-usage")  # required for GitHub Actions
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0.0.0 Safari/537.36")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


# ─────────────────────────────────────────────
#  Popup / modal dismisser
# ─────────────────────────────────────────────
def dismiss_popups(driver, timeout=3):
    dismissed = 0
    CLOSE_SELECTORS = [
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'skip')]",
        "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'skip')]",
        "//span[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'skip')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'maybe later')]",
        "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'maybe later')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'not now')]",
        "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'not now')]",
        "//button[normalize-space(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'))='later']",
        "//*[contains(@class,'close-btn') or contains(@class,'closeBtn') or contains(@class,'cross-btn')]",
        "//*[contains(@class,'crossIcon') or contains(@class,'cross-icon')]",
        "//*[contains(@class,'modal-close') or contains(@class,'modalClose')]",
        "//button[@aria-label='Close' or @aria-label='close' or @aria-label='Dismiss']",
        "//button[.//svg and contains(@class,'close')]",
        "//*[contains(@class,'overlayClose')]",
        "//*[@data-testid='modal-close']",
        "//*[@data-testid='close-button']",
        "//div[contains(@class,'app-download')]//button",
        "//div[contains(@class,'appDownload')]//button",
        "//*[contains(@class,'nudge')]//button[contains(@class,'close') or contains(text(),'×') or contains(text(),'✕')]",
        "//div[contains(@class,'loginModal')]//button[contains(@class,'close') or contains(text(),'×')]",
        "//div[contains(@class,'login-modal')]//button",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'got it')]",
        "//button[normalize-space(text())='×' or normalize-space(text())='✕' or normalize-space(text())='✖']",
    ]

    for attempt in range(4):
        found_this_pass = False
        for xpath in CLOSE_SELECTORS:
            try:
                elements = driver.find_elements(By.XPATH, xpath)
                for el in elements:
                    if el.is_displayed() and el.is_enabled():
                        try:
                            driver.execute_script("arguments[0].click();", el)
                            time.sleep(0.6)
                            dismissed += 1
                            found_this_pass = True
                            log.info(f"  [popup] Dismissed via: {xpath[:60]}...")
                            break
                        except Exception:
                            pass
                if found_this_pass:
                    break
            except Exception:
                continue
        if not found_this_pass:
            break

    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.4)
    except Exception:
        pass

    if dismissed:
        log.info(f"  [popup] Total dismissed: {dismissed}")
    return dismissed


# ─────────────────────────────────────────────
#  Login
# ─────────────────────────────────────────────
def login(driver, email, password):
    log.info("Logging in to Naukri...")
    driver.get("https://www.naukri.com/nlogin/login")
    wait = WebDriverWait(driver, 15)

    try:
        email_field = wait.until(EC.presence_of_element_located((By.ID, "usernameField")))
        email_field.clear()
        email_field.send_keys(email)

        pwd_field = driver.find_element(By.ID, "passwordField")
        pwd_field.clear()
        pwd_field.send_keys(password)

        login_btn = driver.find_element(By.XPATH, "//button[@type='submit']")
        login_btn.click()

        wait.until(EC.url_contains("naukri.com"))
        time.sleep(CONFIG["action_delay"])
        log.info("Login successful!")
        dismiss_popups(driver)
        return True

    except TimeoutException:
        log.error("Login failed — check credentials or if Naukri changed its UI.")
        return False


# ─────────────────────────────────────────────
#  Search jobs
# ─────────────────────────────────────────────
def search_jobs(driver, keyword, location):
    log.info(f"Searching: '{keyword}' in '{location}'...")
    url = (
        f"https://www.naukri.com/{keyword.lower().replace(' ', '-')}-jobs-in-"
        f"{location.lower()}?experienceRanges={CONFIG['experience_min']}%20to%20"
        f"{CONFIG['experience_max']}&jobAge=3"
    )
    driver.get(url)
    time.sleep(CONFIG["action_delay"])
    dismiss_popups(driver)

    for _ in range(3):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)

    try:
        job_cards = driver.find_elements(By.CLASS_NAME, "cust-job-tuple")
        log.info(f"Found {len(job_cards)} job listings")
        return job_cards
    except NoSuchElementException:
        log.warning("No job cards found.")
        return []


# ─────────────────────────────────────────────
#  Check if job matches preferences
# ─────────────────────────────────────────────
def is_matching_job(title, description):
    title_lower = title.lower()
    desc_lower = description.lower()

    for ex in CONFIG["exclude_keywords"]:
        if ex.lower() in title_lower:
            log.info(f"  Skipping (excluded keyword '{ex}'): {title}")
            return False

    for skill in CONFIG["required_skills"]:
        if skill.lower() in title_lower or skill.lower() in desc_lower:
            return True

    log.info(f"  Skipping (no skill match): {title}")
    return False


# ─────────────────────────────────────────────
#  Apply to a single job
# ─────────────────────────────────────────────
def apply_to_job(driver, job_url, job_title, applied_log):
    if job_url in applied_log:
        log.info(f"  Already applied: {job_title}")
        return False

    original_window = driver.current_window_handle
    driver.execute_script(f"window.open('{job_url}', '_blank');")
    driver.switch_to.window(driver.window_handles[-1])
    time.sleep(CONFIG["action_delay"])

    wait = WebDriverWait(driver, 10)

    try:
        dismiss_popups(driver)

        apply_btn = None
        for selector in [
            "//button[contains(text(),'Apply')]",
            "//a[contains(text(),'Apply')]",
            "//button[@id='apply-button']",
            "//*[contains(@class,'apply-button')]",
        ]:
            try:
                apply_btn = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                break
            except TimeoutException:
                continue

        if not apply_btn:
            log.warning(f"  No Apply button found: {job_title}")
            driver.close()
            driver.switch_to.window(original_window)
            return False

        apply_btn.click()
        time.sleep(1.5)
        dismiss_popups(driver)

        try:
            confirm = WebDriverWait(driver, 4).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Apply')]"))
            )
            confirm.click()
            time.sleep(1)
        except TimeoutException:
            pass

        log.info(f"  ✅ Applied: {job_title}")
        applied_log[job_url] = {
            "title": job_title,
            "applied_at": datetime.now().isoformat(),
            "url": job_url,
        }
        driver.close()
        driver.switch_to.window(original_window)
        return True

    except ElementClickInterceptedException:
        log.warning(f"  Click blocked: {job_title}")
        driver.close()
        driver.switch_to.window(original_window)
        return False
    except Exception as e:
        log.error(f"  Error applying to {job_title}: {e}")
        driver.close()
        driver.switch_to.window(original_window)
        return False


# ─────────────────────────────────────────────
#  Main agent loop
# ─────────────────────────────────────────────
def run_agent():
    if not CONFIG["email"] or not CONFIG["password"]:
        log.error("NAUKRI_EMAIL or NAUKRI_PASSWORD not set in environment variables!")
        return

    applied_log = load_applied(CONFIG["log_file"])
    log.info(f"Loaded {len(applied_log)} previously applied jobs")

    driver = create_driver()

    try:
        if not login(driver, CONFIG["email"], CONFIG["password"]):
            return

        total_applied = 0

        for keyword in CONFIG["search_keywords"]:
            log.info(f"\n{'='*50}")
            log.info(f"Keyword: {keyword}")
            log.info(f"{'='*50}")

            job_cards = search_jobs(driver, keyword, CONFIG["location"])
            applied_this_round = 0

            for card in job_cards:
                if applied_this_round >= CONFIG["max_apply_per_search"]:
                    log.info(f"Reached max ({CONFIG['max_apply_per_search']}) for '{keyword}'")
                    break

                try:
                    title_el = card.find_element(By.CLASS_NAME, "title")
                    job_title = title_el.text.strip()
                    job_url = title_el.get_attribute("href") or card.find_element(
                        By.TAG_NAME, "a"
                    ).get_attribute("href")

                    try:
                        desc = card.find_element(By.CLASS_NAME, "job-description").text
                    except NoSuchElementException:
                        desc = ""

                    log.info(f"Checking: {job_title}")

                    if is_matching_job(job_title, desc):
                        success = apply_to_job(driver, job_url, job_title, applied_log)
                        if success:
                            applied_this_round += 1
                            total_applied += 1
                            save_applied(CONFIG["log_file"], applied_log)
                            time.sleep(CONFIG["action_delay"])

                except Exception as e:
                    log.warning(f"  Skipping card due to error: {e}")
                    continue

        log.info(f"\n{'='*50}")
        log.info(f"Done! Applied to {total_applied} new jobs this session.")
        log.info(f"Total ever applied: {len(applied_log)}")

    finally:
        driver.quit()


if __name__ == "__main__":
    run_agent()
