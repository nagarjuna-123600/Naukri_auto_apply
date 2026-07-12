"""
LinkedIn Auto-Apply Bot  ─  FULL VERSION
=========================================
Features:
  ✅ Auto login (email + password)
  ✅ Easy Apply jobs only (skips external apply)
  ✅ SECTION 1 — Jobs in Hyderabad
  ✅ SECTION 2 — Remote / WFH Jobs (India)
  ✅ SECTION 3 — Internships in Hyderabad
  ✅ SECTION 4 — Remote Internships
  ✅ Skill filter — only applies if required skill matches
  ✅ Exclude filter — skips non-IT, senior, sales roles
  ✅ Fills multi-step Easy Apply forms automatically
  ✅ Duplicate prevention (linkedin_applied_jobs.json)
  ✅ Headless mode for GitHub Actions
  ✅ Full logging to console + linkedin_bot.log

Requirements:
    pip install selenium webdriver-manager schedule

Usage:
    python linkedin_auto_apply.py
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
#  CONFIG
# ═══════════════════════════════════════════════════════════════
CONFIG = {
    # ── LinkedIn login ───────────────────────────────────────────
    "email":    os.getenv("LINKEDIN_EMAIL",    "your_email@example.com"),
    "password": os.getenv("LINKEDIN_PASSWORD", "your_password"),

    # ── Job search ───────────────────────────────────────────────
    "search_keywords": [
        "Java Developer",
        "Python Developer",
        "SQL Developer",
        "Software Engineer",
        "Associate Software Engineer",
        "Data Analyst",
        "AI ML Engineer",
        "Machine Learning Engineer",
    ],
    "location":   "Hyderabad",
    "remote_location": "India",

    # ── Internship keywords ──────────────────────────────────────
    "internship_keywords": [
        "Java Intern",
        "Python Intern",
        "SQL Intern",
        "Data Analyst Intern",
        "Software Engineer Intern",
        "Machine Learning Intern",
    ],

    # ── Skill filter ─────────────────────────────────────────────
    "required_skills": [
        "java", "python", "sql", "mysql", "postgresql",
        "software engineer", "associate software engineer",
        "software developer", "java developer", "python developer",
        "sql developer", "junior developer",
        "langchain", "rag", "huggingface", "faiss", "streamlit",
        "machine learning", "deep learning",
        "artificial intelligence", "natural language processing", "nlp",
        "data analyst", "data science",
        "it fresher", "software fresher", "tech fresher",
        "it trainee", "software trainee", "developer trainee",
        "it intern", "software intern", "developer intern",
        "computer science", "information technology",
    ],

    # ── Exclude keywords ─────────────────────────────────────────
    "exclude_keywords": [
        "senior", "lead", "manager", "architect", "principal",
        "web developer", "frontend developer", "front-end developer",
        "backend developer", "back-end developer",
        "full stack developer", "fullstack developer",
        "sales", "marketing", "hr ", "human resource", "recruiter",
        "accountant", "accounting", "finance", "financial",
        "content writer", "digital marketing", "seo",
        "customer support", "customer care", "customer service",
        "telecaller", "telesales", "bpo",
        "civil engineer", "mechanical engineer", "electrical engineer",
        "hardware engineer", "network engineer", "field engineer",
        "electronics engineer", "embedded engineer",
        "production engineer", "manufacturing engineer",
        "teacher", "trainer", "faculty", "professor",
        "doctor", "nurse", "pharmacist", "medical",
        "legal", "lawyer", "advocate",
        "logistics", "supply chain", "warehouse",
        "graphic designer", "ui designer", "ux designer",
        "business development", "relationship manager",
        "banking", "insurance", "loan",
        "mechanical", "electrical maintenance",
        "embedded", "vlsi",
    ],

    # ── Form answers ─────────────────────────────────────────────
    "phone":              os.getenv("PHONE_NUMBER", "9999999999"),
    "current_ctc":        "3",
    "expected_ctc":       "5",
    "notice_period_days": 15,
    "years_of_experience": "0",
    "cover_letter":       "I am a fresher with strong skills in Python, Java, SQL, and AI/ML. I am eager to contribute and grow with your team.",

    # ── Limits ───────────────────────────────────────────────────
    "max_apply_per_search": 10,
    "action_delay":          2,
    "log_file": "linkedin_applied_jobs.json",
    "headless": False,
}


# ═══════════════════════════════════════════════════════════════
#  Logging
# ═══════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("linkedin_bot.log"),
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
            log.warning("linkedin_applied_jobs.json was corrupt — starting fresh")
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
    is_ci = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"

    if is_ci or CONFIG["headless"]:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--remote-debugging-port=9223")
        log.info("  [driver] Headless mode")
    else:
        options.add_argument("--start-maximized")
        log.info("  [driver] Visible mode")

    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--lang=en-US,en;q=0.9")
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    service = Service(ChromeDriverManager().install())
    driver  = webdriver.Chrome(service=service, options=options)

    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        window.chrome = {runtime: {}};
    """})
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(5)
    return driver


# ═══════════════════════════════════════════════════════════════
#  Popup dismisser
# ═══════════════════════════════════════════════════════════════
def dismiss_popups(driver):
    CLOSE_SELECTORS = [
        "button[aria-label='Dismiss']",
        "button[aria-label='Close']",
        ".artdeco-modal__dismiss",
        ".msg-overlay-bubble-header__controls button",
        "button.contextual-sign-in-modal__modal-dismiss",
        ".contextual-sign-in-modal__modal-dismiss",
        "[data-test-modal-close-btn]",
        ".artdeco-toast-item__dismiss",
    ]
    dismissed = 0
    for sel in CLOSE_SELECTORS:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                if el.is_displayed():
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(0.5)
                    dismissed += 1
        except Exception:
            continue
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.3)
    except Exception:
        pass
    return dismissed


# ═══════════════════════════════════════════════════════════════
#  Login
# ═══════════════════════════════════════════════════════════════
def login(driver, email, password):
    log.info("Logging into LinkedIn...")
    driver.get("https://www.linkedin.com/login")
    wait = WebDriverWait(driver, 20)
    time.sleep(3)
    try:
        email_field = wait.until(EC.element_to_be_clickable((By.ID, "username")))
        email_field.clear()
        email_field.send_keys(email)
        time.sleep(0.5)

        pwd_field = driver.find_element(By.ID, "password")
        pwd_field.clear()
        pwd_field.send_keys(password)
        time.sleep(0.5)

        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(5)

        if "feed" in driver.current_url or "mynetwork" in driver.current_url:
            log.info("✅ LinkedIn login successful!")
            dismiss_popups(driver)
            return True
        else:
            log.error(f"❌ Login failed — current URL: {driver.current_url}")
            return False
    except Exception as e:
        log.error(f"❌ Login error: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
#  Skill filter
# ═══════════════════════════════════════════════════════════════
def is_matching_job(title, description=""):
    title_lower = title.lower()
    desc_lower  = description.lower()

    for ex in CONFIG["exclude_keywords"]:
        if ex.lower() in title_lower:
            log.info(f"  Skipping (excluded '{ex}'): {title}")
            return False

    for skill in CONFIG["required_skills"]:
        if skill.lower() in title_lower or skill.lower() in desc_lower:
            return True

    log.info(f"  Skipping (no skill match): {title}")
    return False


# ═══════════════════════════════════════════════════════════════
#  Easy Apply form handler
# ═══════════════════════════════════════════════════════════════
def handle_easy_apply_form(driver):
    wait = WebDriverWait(driver, 8)
    form_filled = False

    for step in range(8):
        time.sleep(1.5)
        dismiss_popups(driver)

        # Fill phone number
        for phone_sel in [
            "input[id*='phoneNumber']",
            "input[name*='phone']",
            "input[placeholder*='phone']",
            "input[placeholder*='Phone']",
        ]:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, phone_sel)
                for el in els:
                    if el.is_displayed() and el.is_enabled():
                        val = el.get_attribute("value") or ""
                        if not val.strip():
                            el.clear()
                            el.send_keys(CONFIG["phone"])
                            form_filled = True
            except Exception:
                pass

        # Fill text inputs (CTC, experience, etc.)
        try:
            inputs = driver.find_elements(By.CSS_SELECTOR,
                "input[type='text']:not([readonly]), input[type='number']:not([readonly])"
            )
            for el in inputs:
                if not el.is_displayed() or not el.is_enabled():
                    continue
                label_text = ""
                try:
                    fid = el.get_attribute("id") or ""
                    if fid:
                        lbl = driver.find_element(By.CSS_SELECTOR, f"label[for='{fid}']")
                        label_text = lbl.text.strip().lower()
                except Exception:
                    pass
                if not label_text:
                    label_text = (el.get_attribute("placeholder") or "").lower()
                if not label_text:
                    label_text = (el.get_attribute("aria-label") or "").lower()

                val = el.get_attribute("value") or ""
                if val.strip():
                    continue  # already filled

                if any(k in label_text for k in ["current ctc", "current salary", "ctc"]):
                    el.send_keys(CONFIG["current_ctc"])
                    form_filled = True
                elif any(k in label_text for k in ["expected ctc", "expected salary"]):
                    el.send_keys(CONFIG["expected_ctc"])
                    form_filled = True
                elif any(k in label_text for k in ["year", "experience", "exp"]):
                    el.send_keys(CONFIG["years_of_experience"])
                    form_filled = True
        except Exception:
            pass

        # Fill dropdowns
        try:
            selects = driver.find_elements(By.CSS_SELECTOR, "select")
            for sel_el in selects:
                if not sel_el.is_displayed():
                    continue
                sel = Select(sel_el)
                opts = [o.text.lower() for o in sel.options]
                # Notice period
                if any("notice" in o or "immediate" in o or "days" in o for o in opts):
                    for opt in sel.options:
                        txt = opt.text.lower()
                        if "immediate" in txt or "0" in txt or "15" in txt:
                            sel.select_by_visible_text(opt.text)
                            form_filled = True
                            break
        except Exception:
            pass

        # Fill textareas (cover letter)
        try:
            areas = driver.find_elements(By.CSS_SELECTOR, "textarea")
            for area in areas:
                if not area.is_displayed():
                    continue
                val = area.get_attribute("value") or area.text or ""
                if not val.strip() and CONFIG["cover_letter"]:
                    area.click()
                    area.send_keys(CONFIG["cover_letter"])
                    form_filled = True
        except Exception:
            pass

        # Handle radio buttons (Yes/No questions — default to "Yes" or first option)
        try:
            radios = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
            for radio in radios:
                if not radio.is_displayed():
                    continue
                lbl_text = ""
                try:
                    rid = radio.get_attribute('id') or ''

                    lbl = driver.find_element(By.XPATH, "//label[@for='" + rid + "']")

                    lbl_text = lbl.text.lower()
                except Exception:
                    pass
                if "yes" in lbl_text and not radio.is_selected():
                    driver.execute_script("arguments[0].click();", radio)
                    form_filled = True
        except Exception:
            pass

        # Click Next / Review / Submit
        clicked_next = False
        for btn_text in ["Submit application", "Review", "Next", "Continue", "Done"]:
            try:
                btn = wait.until(EC.element_to_be_clickable((By.XPATH,
                    f"//button[contains(.,'{btn_text}')]"
                )))
                log.info(f"  [form] Clicking: {btn_text}")
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(2)
                clicked_next = True
                form_filled = True

                if btn_text in ["Submit application", "Done"]:
                    log.info("  [form] ✅ Application submitted!")
                    return True
                break
            except TimeoutException:
                continue

        if not clicked_next:
            # Check if already on confirmation screen
            try:
                confirmation = driver.find_element(By.XPATH,
                    "//*[contains(text(),'application was sent') or "
                    "contains(text(),'applied') or contains(text(),'submitted')]"
                )
                log.info("  [form] ✅ Application confirmed!")
                return True
            except NoSuchElementException:
                pass
            break

    return form_filled


# ═══════════════════════════════════════════════════════════════
#  Apply to a single job
# ═══════════════════════════════════════════════════════════════
def apply_to_job(driver, job_url, job_title, applied_log):
    if job_url in applied_log:
        log.info(f"  Already applied: {job_title}")
        return False

    driver.get(job_url)
    time.sleep(CONFIG["action_delay"])
    wait = WebDriverWait(driver, 10)
    dismiss_popups(driver)

    try:
        # Check job description for skill match
        try:
            desc_el = driver.find_element(By.CSS_SELECTOR,
                ".jobs-description__content, .description__text, #job-details"
            )
            desc_text = desc_el.text
        except NoSuchElementException:
            desc_text = ""

        if not is_matching_job(job_title, desc_text):
            return False

        # Look for Easy Apply button only
        easy_apply_btn = None
        for sel in [
            "//button[contains(@class,'jobs-apply-button') and contains(.,'Easy Apply')]",
            "//button[contains(.,'Easy Apply')]",
            ".//button[contains(@aria-label,'Easy Apply')]",
        ]:
            try:
                easy_apply_btn = wait.until(EC.element_to_be_clickable((By.XPATH, sel)))
                break
            except TimeoutException:
                continue

        if not easy_apply_btn:
            log.info(f"  Skipping (no Easy Apply button): {job_title}")
            return False

        driver.execute_script("arguments[0].scrollIntoView(true);", easy_apply_btn)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", easy_apply_btn)
        log.info(f"  Clicked Easy Apply: {job_title}")
        time.sleep(2)
        dismiss_popups(driver)

        # Handle the form
        submitted = handle_easy_apply_form(driver)

        if submitted:
            log.info(f"  ✅ Applied: {job_title}")
            applied_log[job_url] = {
                "title":      job_title,
                "applied_at": datetime.now().isoformat(),
                "url":        job_url,
            }
            # Close modal
            dismiss_popups(driver)
            return True
        else:
            log.warning(f"  Form not completed: {job_title}")
            dismiss_popups(driver)
            return False

    except ElementClickInterceptedException:
        log.info(f"  Skipping (click blocked): {job_title}")
        dismiss_popups(driver)
        return False
    except Exception as e:
        log.warning(f"  Error on {job_title}: {str(e)[:80]}")
        dismiss_popups(driver)
        return False


# ═══════════════════════════════════════════════════════════════
#  Search and apply
# ═══════════════════════════════════════════════════════════════
def search_and_apply(driver, keyword, location, applied_log, is_remote=False, is_internship=False):
    """
    Build LinkedIn search URL and apply to matching jobs.
    f_AL=true  → Easy Apply only
    f_E=1      → Internship experience level
    f_WT=2     → Remote work type
    f_TPR=r86400 → Posted in last 24 hours
    """
    keyword_enc = keyword.replace(" ", "%20")
    location_enc = location.replace(" ", "%20")

    params = [
        f"keywords={keyword_enc}",
        f"location={location_enc}",
        "f_AL=true",         # Easy Apply only
        "f_TPR=r86400",      # Last 24 hours
        "sortBy=DD",         # Most recent first
    ]
    if is_remote:
        params.append("f_WT=2")       # Remote
    if is_internship:
        params.append("f_E=1")        # Internship experience level

    url = "https://www.linkedin.com/jobs/search/?" + "&".join(params)
    log.info(f"\n{'─'*50}\n{'Internship' if is_internship else 'Job'} search: {keyword} | {location}{'  [REMOTE]' if is_remote else ''}\n{'─'*50}")

    driver.get(url)
    time.sleep(4)
    dismiss_popups(driver)

    # Scroll to load more jobs
    for _ in range(3):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.5)

    # Find job cards
    job_cards = driver.find_elements(By.CSS_SELECTOR,
        ".jobs-search__results-list li, .scaffold-layout__list li"
    )
    log.info(f"  Found {len(job_cards)} listings")

    count = 0
    for card in job_cards:
        if count >= CONFIG["max_apply_per_search"]:
            break
        try:
            # Get title and URL
            link_el = card.find_element(By.CSS_SELECTOR,
                "a.job-card-list__title, a.job-card-container__link, a[class*='job-card']"
            )
            job_title = link_el.text.strip()
            job_url   = link_el.get_attribute("href").split("?")[0]

            if not job_title or not job_url:
                continue

            log.info(f"  Checking: {job_title}")

            # Quick title check before opening
            if not is_matching_job(job_title):
                continue

            success = apply_to_job(driver, job_url, job_title, applied_log)
            if success:
                count += 1
                save_applied(CONFIG["log_file"], applied_log)
                time.sleep(CONFIG["action_delay"])

        except StaleElementReferenceException:
            continue
        except NoSuchElementException:
            continue
        except Exception as e:
            log.warning(f"  Card error: {e}")
            continue

    return count


# ═══════════════════════════════════════════════════════════════
#  Main agent
# ═══════════════════════════════════════════════════════════════
def run_agent():
    log.info("\n" + "=" * 55)
    log.info(f"  LinkedIn Bot Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 55)

    applied_log = load_applied(CONFIG["log_file"])
    log.info(f"Previously applied: {len(applied_log)} jobs")

    driver = create_driver()
    total_applied = 0

    try:
        if not login(driver, CONFIG["email"], CONFIG["password"]):
            log.error("Login failed — stopping.")
            return

        # ── SECTION 1: Regular Jobs — Hyderabad ───────────────────
        log.info("\n" + "█" * 55)
        log.info("  SECTION 1 — Jobs in Hyderabad (Last 24 hrs)")
        log.info("█" * 55)
        for keyword in CONFIG["search_keywords"]:
            n = search_and_apply(driver, keyword, CONFIG["location"], applied_log)
            total_applied += n

        # ── SECTION 2: Remote / WFH Jobs ──────────────────────────
        log.info("\n" + "█" * 55)
        log.info("  SECTION 2 — Remote / WFH Jobs (India)")
        log.info("█" * 55)
        for keyword in CONFIG["search_keywords"]:
            n = search_and_apply(driver, keyword, CONFIG["remote_location"], applied_log, is_remote=True)
            total_applied += n

        # ── SECTION 3: Internships — Hyderabad ────────────────────
        log.info("\n" + "█" * 55)
        log.info("  SECTION 3 — Internships in Hyderabad")
        log.info("█" * 55)
        for keyword in CONFIG["internship_keywords"]:
            n = search_and_apply(driver, keyword, CONFIG["location"], applied_log, is_internship=True)
            total_applied += n

        # ── SECTION 4: Remote Internships ─────────────────────────
        log.info("\n" + "█" * 55)
        log.info("  SECTION 4 — Remote Internships (India)")
        log.info("█" * 55)
        for keyword in CONFIG["internship_keywords"]:
            n = search_and_apply(driver, keyword, CONFIG["remote_location"], applied_log, is_remote=True, is_internship=True)
            total_applied += n

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    log.info("\n" + "=" * 55)
    log.info(f"  Run complete — Applied this session: {total_applied}")
    log.info(f"  Total ever applied: {len(load_applied(CONFIG['log_file']))}")
    log.info("=" * 55)


# ═══════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    is_ci = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"

    if is_ci:
        log.info("GitHub Actions — single run mode")
        run_agent()
    else:
        log.info("Local mode — running now then scheduling...")
        run_agent()
        for t in ["09:00", "18:00"]:
            schedule.every().day.at(t).do(run_agent)
            log.info(f"Scheduled: {t}")
        while True:
            schedule.run_pending()
            time.sleep(30)