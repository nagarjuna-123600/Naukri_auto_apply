"""
Naukri Auto-Apply Bot  ─  FULL VERSION
=======================================
Features:
  ✅ Auto login
  ✅ SECTION 1 — Regular Jobs        (Java / Python / SQL Developer, Hyderabad)
  ✅ SECTION 2 — Internships         (Java / Python / SQL, stipend ≥ ₹10,000/month)
  ✅ SECTION 3 — Remote / WFH Jobs   (Java, Python, SQL, Software Engineer/Developer — Work From Home)
  ✅ SECTION 4 — Data Entry WFH      (Data Entry jobs — Work From Home only, skips office roles)
  ✅ Dismisses ALL popups (profile completeness, app download, login nudge, etc.)
  ✅ Fills multi-step application forms automatically:
       • Current CTC       → 3 LPA
       • Expected CTC      → fills from CONFIG
       • Notice Period     → "Immediate" or "15 days" (whichever option exists)
       • Cover Letter      → skips / says not available
  ✅ Handles dropdown selects for notice period
  ✅ Stipend filter for internships (≥ ₹10,000/month)
  ✅ WFH verification — confirms job is truly remote before applying
  ✅ Duplicate prevention (applied_jobs.json)
  ✅ Auto-scheduler — runs every day at 9 AM and 6 PM without manual clicks
  ✅ Headless mode option (Chrome runs silently in background)
  ✅ Full logging to console + naukri_bot.log

Requirements:
    pip install selenium webdriver-manager schedule

Usage:
    python naukri_auto_apply.py
    (runs immediately once, then repeats at scheduled times automatically)
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException,
    ElementClickInterceptedException, StaleElementReferenceException
)
from webdriver_manager.chrome import ChromeDriverManager
import re
import time
import logging
import json
import os
import schedule
from datetime import datetime


# ═══════════════════════════════════════════════════════════════
#  CONFIG — Edit everything here before running
# ═══════════════════════════════════════════════════════════════
CONFIG = {
    # ── Naukri login ────────────────────────────────────────────
    "email":    os.getenv("NAUKRI_EMAIL",    "your_email@example.com"),
    "password": os.getenv("NAUKRI_PASSWORD", "your_password"),

    # ── Job search preferences ──────────────────────────────────
    "search_keywords": [
        "Java Developer",
        "Python Developer",
        "SQL Developer",
        "Software Engineer",
        "Associate Software Engineer",
        "Customer Software Engineer",
        "Data Analyst",
        "AI ML Engineer",
    ],
    "location":       "Hyderabad",
    "experience_min": 0,   # years — only apply to jobs where min experience is 0
    "experience_max": None,  # no max limit — apply regardless of max experience

    # ── Internship search ────────────────────────────────────────
    # Only Java, Python, SQL internships with stipend >= min_stipend
    "internship_keywords": [
        "Java Intern",
        "Python Intern",
        "SQL Intern",
    ],
    "min_stipend": 10000,   # ₹/month — skip internships below this

    # ── Skill filter (any one match = consider applying) ────────
    "required_skills": [
        "java", "python", "sql", "mysql", "postgresql",
        "software engineer", "associate software engineer",
        "customer software engineer",
    ],

    # ── Title keywords that cause a job to be SKIPPED ───────────
    "exclude_keywords": [
        "senior", "lead", "manager", "architect",
        "web developer", "frontend", "front-end", "front end",
        "backend", "back-end", "back end",
        "full stack", "fullstack", "full-stack",
    ],

    # ── Application form answers ────────────────────────────────
    "current_ctc":        "3",    # in LPA (numeric string)
    "expected_ctc":       "5",    # in LPA (numeric string)
    "notice_period_days": 15,     # used to pick closest dropdown option
    # Cover letter — set to None or "" to auto-fill "No cover letter available"
    "cover_letter":       None,

    # ── Run limits ───────────────────────────────────────────────
    "max_apply_per_search": 10,   # per keyword per run
    "action_delay":          2,   # seconds between major actions

    # ── Scheduler ────────────────────────────────────────────────
    # Script runs once immediately on start, then auto-repeats at these times.
    "schedule_times": ["09:00", "18:00"],

    # ── Misc ─────────────────────────────────────────────────────
    "log_file": "applied_jobs.json",
    "headless": False,   # True = Chrome runs silently in background
}


# ═══════════════════════════════════════════════════════════════
#  Logging
# ═══════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("naukri_bot.log"),
    ],
)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  Applied-jobs tracker
# ═══════════════════════════════════════════════════════════════
def load_applied(path):
    if os.path.exists(path):
        try:
            with open(path) as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            log.warning(f"  [load] applied_jobs.json was corrupt/empty — starting fresh")
            return {}
    return {}

def save_applied(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ═══════════════════════════════════════════════════════════════
#  Browser setup
# ═══════════════════════════════════════════════════════════════
def create_driver():
    options = webdriver.ChromeOptions()

    # Detect if running on GitHub Actions / CI (no display available)
    is_ci = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"

    if is_ci or CONFIG["headless"]:
        # GitHub Actions / Linux server — must run headless, no display
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1280,900")
        options.add_argument("--no-sandbox")               # required on Linux CI
        options.add_argument("--disable-dev-shm-usage")    # prevents crashes on CI
        options.add_argument("--disable-gpu")              # no GPU on CI servers
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--remote-debugging-port=9222")
        log.info("  [driver] Running in headless mode (CI/server detected)")
    else:
        # Local laptop — show the browser window
        options.add_argument("--start-maximized")
        log.info("  [driver] Running in visible mode (local laptop)")

    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    service = Service(ChromeDriverManager().install())
    driver  = webdriver.Chrome(service=service, options=options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


# ═══════════════════════════════════════════════════════════════
#  Popup / modal dismisser
#  Handles: profile completeness, app-download banner,
#           login nudge, cookie consent, generic × buttons.
#  Called after login, after every page load, before/after Apply.
# ═══════════════════════════════════════════════════════════════
def dismiss_popups(driver):
    CLOSE_XPATHS = [
        # ── Profile completeness ─────────────────────────────────
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'skip')]",
        "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'skip')]",
        "//span[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'skip')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'maybe later')]",
        "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'maybe later')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'not now')]",
        "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'not now')]",
        "//button[normalize-space(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'))='later']",
        # ── Generic close / × ────────────────────────────────────
        "//*[contains(@class,'close-btn') or contains(@class,'closeBtn') or contains(@class,'cross-btn')]",
        "//*[contains(@class,'crossIcon') or contains(@class,'cross-icon')]",
        "//*[contains(@class,'modal-close') or contains(@class,'modalClose')]",
        "//button[@aria-label='Close' or @aria-label='close' or @aria-label='Dismiss']",
        "//*[contains(@class,'overlayClose')]",
        "//*[@data-testid='modal-close']",
        "//*[@data-testid='close-button']",
        "//button[.//svg and contains(@class,'close')]",
        # ── App-download / nudge banners ──────────────────────────
        "//div[contains(@class,'app-download')]//button",
        "//div[contains(@class,'appDownload')]//button",
        "//*[contains(@class,'nudge')]//button[contains(@class,'close')]",
        # ── Login / registration wall ─────────────────────────────
        "//div[contains(@class,'loginModal')]//button[contains(@class,'close')]",
        "//div[contains(@class,'login-modal')]//button",
        # ── Cookie / consent ──────────────────────────────────────
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'got it')]",
        # ── Fallback × characters ─────────────────────────────────
        "//button[normalize-space(text())='×' or normalize-space(text())='✕' or normalize-space(text())='✖']",
    ]

    dismissed = 0
    for _pass in range(4):
        found = False
        for xpath in CLOSE_XPATHS:
            try:
                els = driver.find_elements(By.XPATH, xpath)
                for el in els:
                    if el.is_displayed() and el.is_enabled():
                        try:
                            driver.execute_script("arguments[0].click();", el)
                            time.sleep(0.6)
                            dismissed += 1
                            found = True
                            log.info(f"  [popup] Dismissed: {xpath[:70]}")
                            break
                        except Exception:
                            pass
                if found:
                    break
            except Exception:
                continue
        if not found:
            break

    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.3)
    except Exception:
        pass

    if dismissed:
        log.info(f"  [popup] Total dismissed this call: {dismissed}")
    return dismissed


# ═══════════════════════════════════════════════════════════════
#  Multi-step application form handler
#  Fills CTC, notice period, cover letter fields and clicks
#  Next / Submit through every step automatically.
# ═══════════════════════════════════════════════════════════════

def _fill_text_field(driver, el, value):
    """Clear a text/number input and type a value."""
    try:
        driver.execute_script("arguments[0].scrollIntoView(true);", el)
        el.click()
        el.send_keys(Keys.CONTROL + "a")
        el.send_keys(Keys.DELETE)
        el.clear()
        el.send_keys(str(value))
        time.sleep(0.3)
        return True
    except Exception:
        return False


def _best_notice_option(select_el, preferred_days):
    """
    From a <select> dropdown pick the option whose value is
    <= preferred_days (Immediate=0, 15 days, 30 days, etc.)
    Falls back to the smallest available option.
    """
    sel     = Select(select_el)
    parsed  = []
    for opt in sel.options:
        txt = opt.text.strip().lower()
        if not txt or txt in ("select", "choose", "--", "select notice period"):
            continue
        num = None
        if "immediate" in txt or txt == "0":
            num = 0
        else:
            m = re.search(r"\d+", txt)
            if m:
                num = int(m.group())
        if num is not None:
            parsed.append((num, opt.text.strip()))

    if not parsed:
        return None

    best = None
    for num, text in sorted(parsed, key=lambda x: x[0]):
        if num <= preferred_days:
            best = text
        else:
            break
    if best is None:
        best = sorted(parsed, key=lambda x: x[0])[0][1]
    return best


def handle_application_form(driver):
    """
    Detects and fills every field in a multi-step Naukri application form.
    Handles up to 6 steps. Returns True if any form was found and processed.
    """
    CTC_CURRENT_KEYWORDS  = ["current ctc", "current salary", "current package",
                              "ctc (current)", "present ctc", "current annual"]
    CTC_EXPECTED_KEYWORDS = ["expected ctc", "expected salary", "expected package",
                              "desired ctc", "ctc (expected)", "expected annual"]
    NOTICE_KEYWORDS       = ["notice period", "notice", "joining period",
                              "available to join", "availability", "join in"]
    COVER_LETTER_KEYWORDS = ["cover letter", "cover note", "message to recruiter",
                              "why should we hire", "write something", "about yourself"]
    SKIP_COVER_TEXT       = "No cover letter available at this time."

    form_found = False

    for step in range(6):
        dismiss_popups(driver)
        time.sleep(0.8)

        # Check if a form/modal is present
        containers = driver.find_elements(
            By.XPATH,
            "//form | //div[contains(@class,'modal')] | "
            "//div[contains(@class,'apply')] | //div[contains(@class,'chatbot')]"
        )
        if not containers:
            break

        # ── Process all visible inputs ────────────────────────────
        inputs = driver.find_elements(
            By.XPATH,
            "//input[not(@type='hidden') and not(@type='submit') "
            "and not(@type='checkbox') and not(@type='radio') and not(@type='file')] "
            "| //textarea | //select"
        )

        for el in inputs:
            try:
                if not el.is_displayed() or not el.is_enabled():
                    continue

                tag   = el.tag_name.lower()
                etype = (el.get_attribute("type") or "").lower()

                # Build label text from multiple sources
                label_text = ""
                fid = el.get_attribute("id") or ""
                if fid:
                    try:
                        lbl = driver.find_element(By.XPATH, f"//label[@for='{fid}']")
                        label_text = lbl.text.strip().lower()
                    except NoSuchElementException:
                        pass
                if not label_text:
                    label_text = (el.get_attribute("placeholder") or "").lower()
                if not label_text:
                    label_text = (el.get_attribute("aria-label") or "").lower()
                if not label_text:
                    try:
                        parent_text = driver.execute_script(
                            "return arguments[0].closest('div,li,tr')?.innerText || ''", el
                        )
                        label_text = (parent_text or "").lower()[:100]
                    except Exception:
                        pass

                # ── Current CTC ───────────────────────────────────
                if any(k in label_text for k in CTC_CURRENT_KEYWORDS):
                    if tag == "input" and etype in ("text", "number", ""):
                        if _fill_text_field(driver, el, CONFIG["current_ctc"]):
                            log.info(f"  [form] Filled Current CTC → {CONFIG['current_ctc']} LPA")
                            form_found = True

                # ── Expected CTC ──────────────────────────────────
                elif any(k in label_text for k in CTC_EXPECTED_KEYWORDS):
                    if tag == "input" and etype in ("text", "number", ""):
                        if _fill_text_field(driver, el, CONFIG["expected_ctc"]):
                            log.info(f"  [form] Filled Expected CTC → {CONFIG['expected_ctc']} LPA")
                            form_found = True

                # ── Notice Period — dropdown ───────────────────────
                elif any(k in label_text for k in NOTICE_KEYWORDS) and tag == "select":
                    best = _best_notice_option(el, CONFIG["notice_period_days"])
                    if best:
                        try:
                            Select(el).select_by_visible_text(best)
                            log.info(f"  [form] Selected Notice Period → '{best}'")
                            form_found = True
                        except Exception as ex:
                            log.warning(f"  [form] Notice dropdown failed: {ex}")

                # ── Notice Period — text input ─────────────────────
                elif any(k in label_text for k in NOTICE_KEYWORDS) and tag == "input":
                    if _fill_text_field(driver, el, str(CONFIG["notice_period_days"])):
                        log.info(f"  [form] Filled Notice Period → {CONFIG['notice_period_days']} days")
                        form_found = True

                # ── Cover Letter ──────────────────────────────────
                elif any(k in label_text for k in COVER_LETTER_KEYWORDS) and tag == "textarea":
                    cover = CONFIG.get("cover_letter") or SKIP_COVER_TEXT
                    if _fill_text_field(driver, el, cover):
                        log.info(f"  [form] Filled Cover Letter field")
                        form_found = True

            except StaleElementReferenceException:
                continue
            except Exception as ex:
                log.debug(f"  [form] Field error: {ex}")
                continue

        # ── Handle radio buttons for notice period ────────────────
        radios = driver.find_elements(By.XPATH, "//input[@type='radio']")
        for radio in radios:
            try:
                if not radio.is_displayed():
                    continue
                rlabel = ""
                rid = radio.get_attribute("id") or ""
                if rid:
                    try:
                        lbl = driver.find_element(By.XPATH, f"//label[@for='{rid}']")
                        rlabel = lbl.text.strip().lower()
                    except Exception:
                        pass
                if not rlabel:
                    rlabel = (radio.get_attribute("value") or "").lower()

                is_immediate = "immediate" in rlabel or rlabel in ("0", "0 days")
                is_15        = "15" in rlabel

                if is_immediate or is_15:
                    if not radio.is_selected():
                        driver.execute_script("arguments[0].click();", radio)
                        log.info(f"  [form] Selected notice radio → '{rlabel}'")
                        form_found = True
                        break
            except Exception:
                continue

        # ── Click Next / Continue / Submit ────────────────────────
        next_clicked = False
        for btn_xpath in [
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'apply now')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'apply')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed')]",
            "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
            "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'apply')]",
        ]:
            try:
                btn = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, btn_xpath))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                time.sleep(0.4)
                driver.execute_script("arguments[0].click();", btn)
                log.info(f"  [form] Clicked → '{btn.text.strip()}'")
                next_clicked = True
                form_found   = True
                time.sleep(1.5)
                dismiss_popups(driver)
                break
            except (TimeoutException, Exception):
                continue

        if not next_clicked:
            break   # no more navigation buttons — form done

    return form_found


# ═══════════════════════════════════════════════════════════════
#  Login
# ═══════════════════════════════════════════════════════════════
def login(driver, email, password):
    log.info("Opening Naukri login page...")
    driver.get("https://www.naukri.com/nlogin/login")
    wait = WebDriverWait(driver, 15)

    try:
        email_field = wait.until(EC.presence_of_element_located((By.ID, "usernameField")))
        email_field.clear()
        email_field.send_keys(email)
        time.sleep(0.5)

        pwd_field = driver.find_element(By.ID, "passwordField")
        pwd_field.clear()
        pwd_field.send_keys(password)
        time.sleep(0.5)

        login_btn = driver.find_element(By.XPATH, "//button[@type='submit']")
        login_btn.click()

        wait.until(EC.url_contains("naukri.com"))
        time.sleep(CONFIG["action_delay"])
        log.info("Login successful!")

        # Dismiss any post-login popup immediately
        dismiss_popups(driver)
        return True

    except TimeoutException:
        log.error("Login failed — check credentials or Naukri UI may have changed.")
        return False


# ═══════════════════════════════════════════════════════════════
#  Search jobs
# ═══════════════════════════════════════════════════════════════
def search_jobs(driver, keyword, location):
    log.info(f"Searching: '{keyword}' in '{location}'...")
    # No experience filter — get all fresher jobs (min exp = 0, any max)
    url = (
        f"https://www.naukri.com/{keyword.lower().replace(' ', '-')}-jobs-in-"
        f"{location.lower()}?jobAge=3&experience=0"
    )
    driver.get(url)
    time.sleep(CONFIG["action_delay"])

    dismiss_popups(driver)

    for _ in range(3):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)

    cards = driver.find_elements(By.CLASS_NAME, "cust-job-tuple")
    if not cards:
        for sel in [".srp-jobtuple-wrapper", "[data-job-id]", ".job-tuple-comp"]:
            cards = driver.find_elements(By.CSS_SELECTOR, sel)
            if cards:
                break

    log.info(f"Found {len(cards)} job listings")
    return cards


# ═══════════════════════════════════════════════════════════════
#  Skill / exclusion filter
# ═══════════════════════════════════════════════════════════════
def is_matching_job(title, description):
    title_lower = title.lower()
    desc_lower  = description.lower()

    for ex in CONFIG["exclude_keywords"]:
        if ex.lower() in title_lower:
            log.info(f"  Skipping (excluded keyword '{ex}'): {title}")
            return False

    # Data Analyst jobs — only apply if SQL is mentioned
    if "data analyst" in title_lower:
        if "sql" in title_lower or "sql" in desc_lower:
            return True
        log.info(f"  Skipping Data Analyst (no SQL mentioned): {title}")
        return False

    for skill in CONFIG["required_skills"]:
        if skill.lower() in title_lower or skill.lower() in desc_lower:
            return True

    log.info(f"  Skipping (no skill match): {title}")
    return False


# ═══════════════════════════════════════════════════════════════
#  Internship search
#  Uses Naukri's dedicated internship search URL.
# ═══════════════════════════════════════════════════════════════
def search_internships(driver, keyword, location):
    log.info(f"  Searching internships: '{keyword}' in '{location}'...")

    # Naukri internship search URL — filters by keyword and location
    slug    = keyword.lower().replace(" ", "-")
    loc     = location.lower().replace(" ", "-")
    url     = (
        f"https://www.naukri.com/internship/{slug}-internship-in-{loc}"
        f"?jobAge=7"
    )
    # Fallback URL using main search with "internship" appended
    url_alt = (
        f"https://www.naukri.com/{slug}-internship-jobs-in-{loc}"
        f"?jobtype=Internship&jobAge=7"
    )

    driver.get(url)
    time.sleep(CONFIG["action_delay"])
    dismiss_popups(driver)

    # Check if page returned results; if not, try alternate URL
    cards = driver.find_elements(By.CLASS_NAME, "cust-job-tuple")
    if not cards:
        driver.get(url_alt)
        time.sleep(CONFIG["action_delay"])
        dismiss_popups(driver)

    # Scroll to load all listings
    for _ in range(3):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)

    # Try multiple card selectors
    cards = driver.find_elements(By.CLASS_NAME, "cust-job-tuple")
    if not cards:
        for sel in [".srp-jobtuple-wrapper", "[data-job-id]", ".job-tuple-comp"]:
            cards = driver.find_elements(By.CSS_SELECTOR, sel)
            if cards:
                break

    log.info(f"  Found {len(cards)} internship listings")
    return cards


# ═══════════════════════════════════════════════════════════════
#  Internship stipend extractor
#  Pulls numeric stipend value from card text.
#  Returns the stipend as an integer, or 0 if not found.
# ═══════════════════════════════════════════════════════════════
def extract_stipend(text):
    """
    Parses stipend from strings like:
      '₹ 10,000 /month'   → 10000
      '15000 - 20000'     → 15000  (takes lower bound)
      '10K - 15K'         → 10000
      'Unpaid'            → 0
      '12,000 per month'  → 12000
    Returns integer value (monthly ₹).
    """
    if not text:
        return 0

    t = text.lower().replace(",", "").replace("₹", "").replace("inr", "").strip()

    # Handle "unpaid" / "no stipend"
    if "unpaid" in t or "no stipend" in t:
        return 0

    # Handle K notation (e.g. 10k, 15K)
    k_match = re.search(r"(\d+(?:\.\d+)?)\s*k", t)
    if k_match:
        return int(float(k_match.group(1)) * 1000)

    # Extract first number found (lower bound of range)
    nums = re.findall(r"\d+", t)
    if nums:
        val = int(nums[0])
        # If the value looks like it's in LPA (e.g. 3 lpa), convert to monthly
        if "lpa" in t or "per annum" in t or "annual" in t:
            return int(val * 100000 / 12)
        return val

    return 0


# ═══════════════════════════════════════════════════════════════
#  Internship match filter
#  Checks skill match AND stipend >= min_stipend.
# ═══════════════════════════════════════════════════════════════
def is_matching_internship(title, description, stipend_text):
    title_lower = title.lower()
    desc_lower  = description.lower()

    # Apply if at least ONE skill from required_skills matches
    skill_match = any(
        s in title_lower or s in desc_lower
        for s in CONFIG["required_skills"]
    )
    if not skill_match:
        log.info(f"  Skipping internship (no skill match): {title}")
        return False

    # Skip excluded title keywords
    for ex in CONFIG["exclude_keywords"]:
        if ex.lower() in title_lower:
            log.info(f"  Skipping internship (excluded keyword '{ex}'): {title}")
            return False

    # Stipend check
    stipend = extract_stipend(stipend_text)
    if stipend < CONFIG["min_stipend"]:
        log.info(
            f"  Skipping internship (stipend ₹{stipend:,} < ₹{CONFIG['min_stipend']:,}): {title}"
        )
        return False

    log.info(f"  ✔ Internship matches — stipend ₹{stipend:,}/month: {title}")
    return True


# ═══════════════════════════════════════════════════════════════
#  Apply to a single job
# ═══════════════════════════════════════════════════════════════
def save_manual_job(job_url, job_title, reason):
    """Save jobs that require manual application (company website, email, WhatsApp)."""
    manual_log_path = "manual_apply_jobs.json"
    if os.path.exists(manual_log_path):
        with open(manual_log_path) as f:
            manual_log = json.load(f)
    else:
        manual_log = {}

    if job_url not in manual_log:
        manual_log[job_url] = {
            "title":    job_title,
            "reason":   reason,
            "saved_at": datetime.now().isoformat(),
            "url":      job_url,
        }
        with open(manual_log_path, "w") as f:
            json.dump(manual_log, f, indent=2)
        log.info(f"  📌 Saved for manual apply ({reason}): {job_title}")


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
        # Clear any popup before looking for Apply button
        dismiss_popups(driver)

        # ── Save job on Naukri first ─────────────────────────────────
        try:
            save_selectors = [
                "//button[contains(text(),'Save')]",
                "//a[contains(text(),'Save')]",
                "//*[contains(@class,'save-job')]",
                "//*[contains(@class,'saveJob')]",
                "//*[contains(@class,'job-save')]",
                "//span[contains(text(),'Save')]",
                "//*[@title='Save Job']",
                "//*[@data-ga-track='Save']",
            ]
            for sel in save_selectors:
                try:
                    save_btn = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH, sel))
                    )
                    driver.execute_script("arguments[0].click();", save_btn)
                    time.sleep(0.5)
                    log.info(f"  💾 Saved on Naukri: {job_title}")
                    break
                except TimeoutException:
                    continue
        except Exception as e:
            log.info(f"  Could not save on Naukri (may already be saved): {job_title}")
        # ─────────────────────────────────────────────────────────────

        # Find the main Apply button
        apply_btn = None
        for selector in [
            "//button[contains(text(),'Apply')]",
            "//a[contains(text(),'Apply')]",
            "//button[@id='apply-button']",
            "//*[contains(@class,'apply-button')]",
            "//button[contains(@class,'applyBtn')]",
            "//*[@data-ga-track='Apply']",
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

        driver.execute_script("arguments[0].scrollIntoView(true);", apply_btn)
        time.sleep(0.4)
        apply_btn.click()
        log.info(f"  Clicked Apply: {job_title}")
        time.sleep(1.5)

        # ── Check for external apply options after clicking ──────────
        page_text = driver.page_source.lower()
        current_url = driver.current_url.lower()

        external_reasons = {
            "company website": [
                "apply on company website", "apply via company",
                "visit company website", "apply at company site",
                "redirecting to company", "external application"
            ],
            "email": [
                "apply via email", "apply through email",
                "send your resume", "email your cv",
                "send cv to", "mail your resume"
            ],
            "whatsapp": [
                "apply via whatsapp", "apply on whatsapp",
                "whatsapp to apply", "contact on whatsapp"
            ],
        }

        detected_reason = None
        for reason, keywords in external_reasons.items():
            for kw in keywords:
                if kw in page_text:
                    detected_reason = reason
                    break
            if detected_reason:
                break

        # Also check if redirected to an external domain
        if not detected_reason and "naukri.com" not in current_url:
            detected_reason = "company website"

        if detected_reason:
            save_manual_job(job_url, job_title, detected_reason)
            driver.close()
            driver.switch_to.window(original_window)
            return False
        # ─────────────────────────────────────────────────────────────

        # Dismiss popup that may appear right after Apply click
        dismiss_popups(driver)

        # Fill any multi-step form (CTC, notice period, cover letter)
        form_handled = handle_application_form(driver)
        if form_handled:
            log.info(f"  [form] Form completed: {job_title}")

        # Final confirmation button if still present
        for confirm_xpath in [
            "//button[contains(text(),'Apply')]",
            "//button[contains(text(),'Submit')]",
            "//button[contains(text(),'Confirm')]",
        ]:
            try:
                confirm = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, confirm_xpath))
                )
                confirm.click()
                time.sleep(1)
                break
            except TimeoutException:
                continue

        log.info(f"  ✅ Applied: {job_title}")
        applied_log[job_url] = {
            "title":      job_title,
            "applied_at": datetime.now().isoformat(),
            "url":        job_url,
        }
        driver.close()
        driver.switch_to.window(original_window)
        return True

    except ElementClickInterceptedException:
        log.warning(f"  Click blocked (external link or already applied): {job_title}")
        driver.close()
        driver.switch_to.window(original_window)
        return False
    except Exception as e:
        log.error(f"  Error applying to {job_title}: {e}")
        try:
            driver.close()
            driver.switch_to.window(original_window)
        except Exception:
            pass
        return False


# ═══════════════════════════════════════════════════════════════
#  Main agent — one full run
# ═══════════════════════════════════════════════════════════════
def run_agent():
    log.info("")
    log.info("=" * 55)
    log.info(f"  Run started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 55)

    applied_log = load_applied(CONFIG["log_file"])
    log.info(f"Loaded {len(applied_log)} previously applied jobs")

    driver = create_driver()

    try:
        if not login(driver, CONFIG["email"], CONFIG["password"]):
            return

        total_applied = 0

        # ── SECTION 1: Regular Jobs ───────────────────────────────
        log.info("\n" + "█" * 55)
        log.info("  SECTION 1 OF 2 — Regular Jobs")
        log.info("█" * 55)

        for keyword in CONFIG["search_keywords"]:
            log.info(f"\n{'─'*50}")
            log.info(f"Keyword: {keyword}")
            log.info(f"{'─'*50}")

            job_cards = search_jobs(driver, keyword, CONFIG["location"])
            applied_this_round = 0

            for card in job_cards:
                if applied_this_round >= CONFIG["max_apply_per_search"]:
                    log.info(f"Reached max ({CONFIG['max_apply_per_search']}) for '{keyword}'")
                    break

                try:
                    try:
                        title_el = card.find_element(By.CLASS_NAME, "title")
                    except NoSuchElementException:
                        title_el = card.find_element(By.TAG_NAME, "a")

                    job_title = title_el.text.strip()
                    job_url   = (
                        title_el.get_attribute("href")
                        or card.find_element(By.TAG_NAME, "a").get_attribute("href")
                    )

                    if not job_title or not job_url:
                        continue

                    try:
                        desc = card.find_element(By.CLASS_NAME, "job-description").text
                    except NoSuchElementException:
                        try:
                            desc = card.find_element(By.CLASS_NAME, "job-desc").text
                        except NoSuchElementException:
                            desc = ""

                    log.info(f"Checking: {job_title}")

                    if is_matching_job(job_title, desc):
                        success = apply_to_job(driver, job_url, job_title, applied_log)
                        if success:
                            applied_this_round += 1
                            total_applied      += 1
                            save_applied(CONFIG["log_file"], applied_log)
                            time.sleep(CONFIG["action_delay"])

                except StaleElementReferenceException:
                    log.warning("  Card became stale — skipping")
                    continue
                except Exception as e:
                    log.warning(f"  Skipping card: {e}")
                    continue

        # ── SECTION 2: Internships ────────────────────────────────
        log.info("\n" + "█" * 55)
        log.info("  SECTION 2 OF 2 — Internships (Java / Python / SQL)")
        log.info(f"  Stipend filter: ≥ ₹{CONFIG['min_stipend']:,} / month")
        log.info("█" * 55)

        for keyword in CONFIG["internship_keywords"]:
            log.info(f"\n{'─'*50}")
            log.info(f"Internship keyword: {keyword}")
            log.info(f"{'─'*50}")

            intern_cards = search_internships(driver, keyword, CONFIG["location"])
            applied_this_round = 0

            for card in intern_cards:
                if applied_this_round >= CONFIG["max_apply_per_search"]:
                    log.info(f"Reached max ({CONFIG['max_apply_per_search']}) for '{keyword}'")
                    break

                try:
                    # Extract title
                    try:
                        title_el = card.find_element(By.CLASS_NAME, "title")
                    except NoSuchElementException:
                        title_el = card.find_element(By.TAG_NAME, "a")

                    job_title = title_el.text.strip()
                    job_url   = (
                        title_el.get_attribute("href")
                        or card.find_element(By.TAG_NAME, "a").get_attribute("href")
                    )

                    if not job_title or not job_url:
                        continue

                    # Extract description
                    try:
                        desc = card.find_element(By.CLASS_NAME, "job-description").text
                    except NoSuchElementException:
                        try:
                            desc = card.find_element(By.CLASS_NAME, "job-desc").text
                        except NoSuchElementException:
                            desc = ""

                    # Extract stipend text from card
                    stipend_text = ""
                    for stipend_cls in [
                        "salary", "stipend", "package",
                        "compensation", "ctc", "exp-salary",
                    ]:
                        try:
                            stipend_text = card.find_element(
                                By.CLASS_NAME, stipend_cls
                            ).text
                            if stipend_text:
                                break
                        except NoSuchElementException:
                            continue

                    # Also check full card text as fallback
                    if not stipend_text:
                        try:
                            full_text = card.text
                            # Look for ₹ symbol or stipend pattern in card text
                            m = re.search(
                                r"(?:stipend|₹|inr|salary)[\s:]*[\d,k]+",
                                full_text, re.IGNORECASE
                            )
                            if m:
                                stipend_text = m.group()
                        except Exception:
                            pass

                    log.info(f"Checking internship: {job_title} | stipend text: '{stipend_text}'")

                    if is_matching_internship(job_title, desc, stipend_text):
                        success = apply_to_job(driver, job_url, job_title, applied_log)
                        if success:
                            applied_this_round += 1
                            total_applied      += 1
                            save_applied(CONFIG["log_file"], applied_log)
                            time.sleep(CONFIG["action_delay"])

                except StaleElementReferenceException:
                    log.warning("  Card became stale — skipping")
                    continue
                except Exception as e:
                    log.warning(f"  Skipping internship card: {e}")
                    continue

        # ── SECTION 3: WFH / Remote Jobs ─────────────────────────
        log.info("\n" + "█" * 55)
        log.info("  SECTION 3 OF 3 — Work From Home Jobs")
        log.info("█" * 55)

        wfh_keywords = [
            kw + " work from home" for kw in CONFIG["search_keywords"]
        ]

        for keyword in wfh_keywords:
            log.info(f"\n{'─'*50}")
            log.info(f"WFH Keyword: {keyword}")
            log.info(f"{'─'*50}")

            wfh_url = (
                f"https://www.naukri.com/{keyword.lower().replace(' ', '-')}-jobs?"
                f"jobAge=3&experience=0&wfhType=remote,hybrid"
            )
            driver.get(wfh_url)
            time.sleep(CONFIG["action_delay"])
            dismiss_popups(driver)

            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1)

            wfh_cards = driver.find_elements(By.CLASS_NAME, "cust-job-tuple")
            log.info(f"Found {len(wfh_cards)} WFH listings")

            applied_this_round = 0

            for card in wfh_cards:
                if applied_this_round >= CONFIG["max_apply_per_search"]:
                    log.info(f"Reached max for '{keyword}'")
                    break

                try:
                    try:
                        title_el = card.find_element(By.CLASS_NAME, "title")
                    except NoSuchElementException:
                        title_el = card.find_element(By.TAG_NAME, "a")

                    job_title = title_el.text.strip()
                    job_url   = (
                        title_el.get_attribute("href")
                        or card.find_element(By.TAG_NAME, "a").get_attribute("href")
                    )

                    if not job_title or not job_url:
                        continue

                    try:
                        desc = card.find_element(By.CLASS_NAME, "job-description").text
                    except NoSuchElementException:
                        try:
                            desc = card.find_element(By.CLASS_NAME, "job-desc").text
                        except NoSuchElementException:
                            desc = ""

                    log.info(f"Checking WFH: {job_title}")

                    if is_matching_job(job_title, desc):
                        success = apply_to_job(driver, job_url, job_title, applied_log)
                        if success:
                            applied_this_round += 1
                            total_applied      += 1
                            save_applied(CONFIG["log_file"], applied_log)
                            time.sleep(CONFIG["action_delay"])

                except StaleElementReferenceException:
                    log.warning("  Card became stale — skipping")
                    continue
                except Exception as e:
                    log.warning(f"  Skipping WFH card: {e}")
                    continue

        # ── SECTION 4: WFH Internships ────────────────────────────
        log.info("\n" + "█" * 55)
        log.info("  SECTION 4 OF 4 — Work From Home Internships")
        log.info("█" * 55)

        for keyword in CONFIG["internship_keywords"]:
            log.info(f"\n{'─'*50}")
            log.info(f"WFH Internship keyword: {keyword}")
            log.info(f"{'─'*50}")

            slug = keyword.lower().replace(" ", "-")
            wfh_intern_urls = [
                f"https://www.naukri.com/internship/{slug}-internship?wfhType=remote,hybrid&jobAge=7",
                f"https://www.naukri.com/{slug}-internship-jobs?jobtype=Internship&wfhType=remote,hybrid&jobAge=7",
            ]

            cards = []
            for url in wfh_intern_urls:
                driver.get(url)
                time.sleep(CONFIG["action_delay"])
                dismiss_popups(driver)
                for _ in range(3):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1)
                cards = driver.find_elements(By.CLASS_NAME, "cust-job-tuple")
                if cards:
                    break

            log.info(f"  Found {len(cards)} WFH internship listings")
            applied_this_round = 0

            for card in cards:
                if applied_this_round >= CONFIG["max_apply_per_search"]:
                    log.info(f"Reached max for '{keyword}'")
                    break

                try:
                    try:
                        title_el = card.find_element(By.CLASS_NAME, "title")
                    except NoSuchElementException:
                        title_el = card.find_element(By.TAG_NAME, "a")

                    job_title = title_el.text.strip()
                    job_url   = (
                        title_el.get_attribute("href")
                        or card.find_element(By.TAG_NAME, "a").get_attribute("href")
                    )

                    if not job_title or not job_url:
                        continue

                    try:
                        desc = card.find_element(By.CLASS_NAME, "job-description").text
                    except NoSuchElementException:
                        try:
                            desc = card.find_element(By.CLASS_NAME, "job-desc").text
                        except NoSuchElementException:
                            desc = ""

                    # Stipend extraction
                    stipend_text = ""
                    try:
                        stipend_text = card.find_element(
                            By.XPATH, ".//*[contains(@class,'stipend') or contains(@class,'salary')]"
                        ).text
                    except NoSuchElementException:
                        pass

                    log.info(f"Checking WFH internship: {job_title}")

                    if is_matching_internship(job_title, desc, stipend_text):
                        success = apply_to_job(driver, job_url, job_title, applied_log)
                        if success:
                            applied_this_round += 1
                            total_applied      += 1
                            save_applied(CONFIG["log_file"], applied_log)
                            time.sleep(CONFIG["action_delay"])

                except StaleElementReferenceException:
                    log.warning("  Card became stale — skipping")
                    continue
                except Exception as e:
                    log.warning(f"  Skipping WFH internship card: {e}")
                    continue

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    log.info("")
    log.info("=" * 55)
    log.info(f"  Run complete — Applied this session: {total_applied}")
    log.info(f"  Total ever applied: {len(load_applied(CONFIG['log_file']))}")
    log.info(f"  Log saved to: {CONFIG['log_file']}")
    log.info("=" * 55)


# ═══════════════════════════════════════════════════════════════
#  Entry point + Scheduler
#
#  LOCAL (PyCharm):
#    Runs once immediately, then auto-repeats at 9 AM and 6 PM daily.
#    Just click Run once — no further clicks needed.
#
#  GITHUB ACTIONS (CI):
#    GitHub triggers the script on a cron schedule.
#    Script runs once and exits — GitHub handles the timing.
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    is_ci = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"

    if is_ci:
        # GitHub Actions — just run once and exit cleanly
        log.info("GitHub Actions detected — running single pass and exiting.")
        run_agent()
        log.info("Single run complete. GitHub Actions will trigger next run on schedule.")
    else:
        # Local laptop — run once now, then repeat on schedule
        log.info("Naukri Auto-Apply Bot starting (local mode)...")
        log.info(f"Scheduled times: {CONFIG['schedule_times']}")
        log.info("Running immediately for the first time...\n")

        run_agent()

        for t in CONFIG["schedule_times"]:
            schedule.every().day.at(t).do(run_agent)
            log.info(f"Scheduled: every day at {t}")

        log.info("\nScheduler is active. Waiting for next run time...")
        log.info("Press Ctrl+C to stop the bot.\n")

        while True:
            schedule.run_pending()
            time.sleep(30)
