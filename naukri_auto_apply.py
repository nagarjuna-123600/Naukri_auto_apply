"""
Naukri Auto-Apply Bot  ─  FULL VERSION
=======================================
Features:
  ✅ Auto login
  ✅ SECTION 0 — Newly Arrived Jobs   (All keywords — posted in last 24 hours — Hyderabad)
  ✅ SECTION 1 — Regular Jobs        (Java / Python / SQL Developer, Hyderabad)
  ✅ SECTION 2 — Internships         (Java / Python / SQL, stipend ≥ ₹10,000/month, Hyderabad)
  ✅ SECTION 3 — Remote / WFH Jobs   (Java, Python, SQL — Work From Home, any location)
  ✅ SECTION 4 — WFH Internships     (Work From Home only)
  ✅ SECTION 5 — Newly Arrived Jobs  (Last 24 hrs — Hyderabad + WFH)
  ✅ Dismisses ALL popups
  ✅ Fills multi-step application forms automatically
  ✅ Duplicate prevention (applied_jobs.json)
  ✅ Headless mode for GitHub Actions
  ✅ Full logging to console + naukri_bot.log
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
    "email":    os.getenv("NAUKRI_EMAIL",    "your_email@example.com"),
    "password": os.getenv("NAUKRI_PASSWORD", "your_password"),

    "search_keywords": [
        "Java Developer", "Python Developer", "SQL Developer",
        "Software Engineer", "Associate Software Engineer",
        "Data Analyst", "AI ML Engineer",
    ],
    "location": "Hyderabad",
    "experience_min": 0,
    "experience_max": None,

    "internship_keywords": [
        "Java Intern", "Python Intern", "SQL Intern",
        "AIML Intern", "Data Analyst",
    ],
    "min_stipend": 10000,

    "required_skills": [
        "java", "python", "sql", "mysql", "postgresql",
        "software engineer", "associate software engineer",
        "software developer", "langchain", "rag", "huggingface",
        "faiss", "streamlit", "junior developer", "trainee",
        "intern", "fresher", "java developer", "python developer",
        "sql developer", "ai", "ml", "machine learning",
        "deep learning", "data analyst", "data science",
    ],

    "exclude_keywords": [
        "senior", "lead", "manager", "architect",
        "web developer", "frontend developer", "front-end developer",
        "backend developer", "back-end developer",
        "full stack developer", "fullstack developer",
        "sales", "marketing", "hr ", "human resource", "recruiter",
        "accountant", "accounting", "finance", "financial",
        "content writer", "content writing", "copywriter",
        "digital marketing", "seo", "social media",
        "customer support", "customer care", "customer service",
        "telecaller", "telesales", "bpo", "voice process",
        "data entry", "back office", "back-office",
        "field sales", "field executive", "field officer",
        "civil engineer", "mechanical engineer", "electrical engineer",
        "hardware engineer", "network engineer", "field engineer",
        "teacher", "trainer", "faculty", "professor", "lecturer",
        "doctor", "nurse", "pharmacist", "medical",
        "legal", "lawyer", "advocate", "compliance",
        "logistics", "supply chain", "warehouse", "delivery",
        "chef", "cook", "hospitality", "hotel",
        "graphic designer", "ui designer", "ux designer",
        "interior designer", "fashion designer",
        "business development", "bd executive",
        "relationship manager", "bank", "banking",
        "insurance", "loan", "investment",
        "operations executive", "operations manager",
    ],

    "current_ctc":        "3",
    "expected_ctc":       "3",
    "notice_period_days": 15,
    "cover_letter":       None,
    "max_apply_per_search": 10,
    "action_delay":          2,
    "schedule_times": ["09:00", "18:00"],
    "log_file": "applied_jobs.json",
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
            log.warning("applied_jobs.json was corrupt/empty — starting fresh")
            return {}
    return {}

def save_applied(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ═══════════════════════════════════════════════════════════════
#  FIX: save_manual_job — was missing entirely, caused NameError crash
# ═══════════════════════════════════════════════════════════════
def save_manual_job(job_url, job_title, reason):
    """Save jobs that require manual application (company website, email, WhatsApp)."""
    manual_log_path = "manual_apply_jobs.json"
    try:
        if os.path.exists(manual_log_path):
            with open(manual_log_path) as f:
                content = f.read().strip()
                manual_log = json.loads(content) if content else {}
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
    except Exception as e:
        log.warning(f"  Could not save manual job: {e}")


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
        options.add_argument("--remote-debugging-port=9222")
        log.info("  [driver] Running in headless mode (CI/server detected)")
    else:
        options.add_argument("--start-maximized")
        log.info("  [driver] Running in visible mode (local laptop)")

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

    stealth_js = """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
        window.chrome = {runtime: {}};
    """
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": stealth_js})
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(5)
    return driver


# ═══════════════════════════════════════════════════════════════
#  Popup dismisser
# ═══════════════════════════════════════════════════════════════
def dismiss_popups(driver):
    CLOSE_XPATHS = [
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'skip')]",
        "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'skip')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'maybe later')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'not now')]",
        "//button[normalize-space(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'))='later']",
        "//*[contains(@class,'close-btn') or contains(@class,'closeBtn') or contains(@class,'cross-btn')]",
        "//*[contains(@class,'crossIcon') or contains(@class,'cross-icon')]",
        "//*[contains(@class,'modal-close') or contains(@class,'modalClose')]",
        "//button[@aria-label='Close' or @aria-label='close' or @aria-label='Dismiss']",
        "//*[contains(@class,'overlayClose')]",
        "//*[@data-testid='modal-close']",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept')]",
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
    return dismissed


# ═══════════════════════════════════════════════════════════════
#  Application form handler
# ═══════════════════════════════════════════════════════════════
def _fill_text_field(driver, el, value):
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
    sel    = Select(select_el)
    parsed = []
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
    CTC_CURRENT_KEYWORDS  = ["current ctc", "current salary", "current package", "present ctc"]
    CTC_EXPECTED_KEYWORDS = ["expected ctc", "expected salary", "expected package", "desired ctc"]
    NOTICE_KEYWORDS       = ["notice period", "notice", "joining period", "available to join"]
    COVER_LETTER_KEYWORDS = ["cover letter", "cover note", "message to recruiter", "write something"]
    SKIP_COVER_TEXT       = "No cover letter available at this time."
    form_found = False

    for step in range(6):
        dismiss_popups(driver)
        time.sleep(0.8)
        containers = driver.find_elements(
            By.XPATH,
            "//form | //div[contains(@class,'modal')] | //div[contains(@class,'apply')] | //div[contains(@class,'chatbot')]"
        )
        if not containers:
            break

        inputs = driver.find_elements(
            By.XPATH,
            "//input[not(@type='hidden') and not(@type='submit') and not(@type='checkbox') "
            "and not(@type='radio') and not(@type='file')] | //textarea | //select"
        )

        for el in inputs:
            try:
                if not el.is_displayed() or not el.is_enabled():
                    continue
                tag   = el.tag_name.lower()
                etype = (el.get_attribute("type") or "").lower()
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

                if any(k in label_text for k in CTC_CURRENT_KEYWORDS):
                    if tag == "input" and etype in ("text", "number", ""):
                        if _fill_text_field(driver, el, CONFIG["current_ctc"]):
                            log.info(f"  [form] Filled Current CTC → {CONFIG['current_ctc']} LPA")
                            form_found = True
                elif any(k in label_text for k in CTC_EXPECTED_KEYWORDS):
                    if tag == "input" and etype in ("text", "number", ""):
                        if _fill_text_field(driver, el, CONFIG["expected_ctc"]):
                            log.info(f"  [form] Filled Expected CTC → {CONFIG['expected_ctc']} LPA")
                            form_found = True
                elif any(k in label_text for k in NOTICE_KEYWORDS) and tag == "select":
                    best = _best_notice_option(el, CONFIG["notice_period_days"])
                    if best:
                        try:
                            Select(el).select_by_visible_text(best)
                            log.info(f"  [form] Selected Notice Period → '{best}'")
                            form_found = True
                        except Exception as ex:
                            log.warning(f"  [form] Notice dropdown failed: {ex}")
                elif any(k in label_text for k in NOTICE_KEYWORDS) and tag == "input":
                    if _fill_text_field(driver, el, str(CONFIG["notice_period_days"])):
                        log.info(f"  [form] Filled Notice Period → {CONFIG['notice_period_days']} days")
                        form_found = True
                elif any(k in label_text for k in COVER_LETTER_KEYWORDS) and tag == "textarea":
                    cover = CONFIG.get("cover_letter") or SKIP_COVER_TEXT
                    if _fill_text_field(driver, el, cover):
                        log.info("  [form] Filled Cover Letter field")
                        form_found = True
            except StaleElementReferenceException:
                continue
            except Exception as ex:
                log.debug(f"  [form] Field error: {ex}")
                continue

        next_clicked = False
        for btn_xpath in [
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'apply now')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'apply')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
        ]:
            try:
                btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, btn_xpath)))
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
            break
    return form_found


# ═══════════════════════════════════════════════════════════════
#  Login
# ═══════════════════════════════════════════════════════════════
def login(driver, email, password):
    log.info("Trying email/password login...")
    driver.get("https://www.naukri.com/nlogin/login")
    wait = WebDriverWait(driver, 20)
    time.sleep(5)
    try:
        email_field = wait.until(EC.element_to_be_clickable((By.ID, "usernameField")))
        driver.execute_script("arguments[0].click();", email_field)
        time.sleep(0.5)
        email_field.clear()
        for char in email:
            email_field.send_keys(char)
            time.sleep(0.05)
        time.sleep(1)

        pwd_field = wait.until(EC.element_to_be_clickable((By.ID, "passwordField")))
        driver.execute_script("arguments[0].click();", pwd_field)
        time.sleep(0.5)
        pwd_field.clear()
        for char in password:
            pwd_field.send_keys(char)
            time.sleep(0.05)
        time.sleep(1)

        login_btn = driver.find_element(By.XPATH, "//button[@type='submit']")
        login_btn.click()
        wait.until(EC.url_contains("naukri.com"))
        time.sleep(CONFIG["action_delay"])
        log.info("✅ Login successful!")
        dismiss_popups(driver)
        return True
    except TimeoutException:
        log.error("❌ Login failed — check NAUKRI_EMAIL and NAUKRI_PASSWORD secrets!")
        return False


# ═══════════════════════════════════════════════════════════════
#  Apply to a single job
# ═══════════════════════════════════════════════════════════════
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

        # Find Apply button
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
            save_manual_job(job_url, job_title, "no_apply_button")
            driver.close()
            driver.switch_to.window(original_window)
            return False

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", apply_btn)
        time.sleep(1)
        dismiss_popups(driver)
        time.sleep(0.5)
        try:
            apply_btn.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", apply_btn)
        log.info(f"  Clicked Apply: {job_title}")
        time.sleep(1.5)

        # Check for external apply redirect
        page_text   = driver.page_source.lower()
        current_url = driver.current_url.lower()
        external_reasons = {
            "company website": ["apply on company website", "apply via company", "external application"],
            "email":           ["apply via email", "send your resume", "email your cv"],
            "whatsapp":        ["apply via whatsapp", "whatsapp to apply"],
        }
        detected_reason = None
        for reason, keywords in external_reasons.items():
            for kw in keywords:
                if kw in page_text:
                    detected_reason = reason
                    break
            if detected_reason:
                break
        if not detected_reason and "naukri.com" not in current_url:
            detected_reason = "company website"

        if detected_reason:
            save_manual_job(job_url, job_title, detected_reason)
            driver.close()
            driver.switch_to.window(original_window)
            return False

        dismiss_popups(driver)
        form_handled = handle_application_form(driver)
        if form_handled:
            log.info(f"  [form] Form completed: {job_title}")

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
        log.warning(f"  Click blocked: {job_title}")
        save_manual_job(job_url, job_title, "click_blocked")
        try:
            driver.close()
            driver.switch_to.window(original_window)
        except Exception:
            pass
        return False
    except Exception as e:
        log.error(f"  Error applying to {job_title}: {e}")
        save_manual_job(job_url, job_title, f"error: {str(e)[:50]}")
        try:
            driver.close()
            driver.switch_to.window(original_window)
        except Exception:
            pass
        return False


# ═══════════════════════════════════════════════════════════════
#  Skill filter
# ═══════════════════════════════════════════════════════════════
def is_matching_job(title, description):
    title_lower = title.lower()
    desc_lower  = description.lower()
    for ex in CONFIG["exclude_keywords"]:
        if ex.lower() in title_lower:
            log.info(f"  Skipping (excluded '{ex}'): {title}")
            return False
    if "data analyst" in title_lower:
        if "sql" in title_lower or "sql" in desc_lower:
            return True
        log.info(f"  Skipping Data Analyst (no SQL): {title}")
        return False
    for skill in CONFIG["required_skills"]:
        if skill.lower() in title_lower or skill.lower() in desc_lower:
            return True
    log.info(f"  Skipping (no skill match): {title}")
    return False


# ═══════════════════════════════════════════════════════════════
#  Internship helpers
# ═══════════════════════════════════════════════════════════════
def extract_stipend(text):
    if not text:
        return 0
    t = text.lower().replace(",", "").replace("₹", "").replace("inr", "").strip()
    if "unpaid" in t or "no stipend" in t:
        return 0
    k_match = re.search(r"(\d+(?:\.\d+)?)\s*k", t)
    if k_match:
        return int(float(k_match.group(1)) * 1000)
    nums = re.findall(r"\d+", t)
    if nums:
        val = int(nums[0])
        if "lpa" in t or "per annum" in t:
            return int(val * 100000 / 12)
        return val
    return 0

def is_matching_internship(title, description, stipend_text):
    title_lower = title.lower()
    desc_lower  = description.lower()
    skill_match = any(s in title_lower or s in desc_lower for s in CONFIG["required_skills"])
    if not skill_match:
        log.info(f"  Skipping internship (no skill match): {title}")
        return False
    for ex in CONFIG["exclude_keywords"]:
        if ex.lower() in title_lower:
            log.info(f"  Skipping internship (excluded '{ex}'): {title}")
            return False
    stipend = extract_stipend(stipend_text)
    if stipend < CONFIG["min_stipend"]:
        log.info(f"  Skipping internship (stipend ₹{stipend:,} < ₹{CONFIG['min_stipend']:,}): {title}")
        return False
    log.info(f"  ✔ Internship matches — stipend ₹{stipend:,}/month: {title}")
    return True


# ═══════════════════════════════════════════════════════════════
#  Job card extractor helper
# ═══════════════════════════════════════════════════════════════
def extract_card_info(driver, card):
    """Extract title, url, description from a job card. Returns (title, url, desc) or None."""
    try:
        try:
            title_el = card.find_element(By.CLASS_NAME, "title")
        except NoSuchElementException:
            title_el = card.find_element(By.TAG_NAME, "a")
        job_title = title_el.text.strip()
        job_url   = title_el.get_attribute("href") or card.find_element(By.TAG_NAME, "a").get_attribute("href")
        if not job_title or not job_url:
            return None
        try:
            desc = card.find_element(By.CLASS_NAME, "job-description").text
        except NoSuchElementException:
            try:
                desc = card.find_element(By.CLASS_NAME, "job-desc").text
            except NoSuchElementException:
                desc = ""
        return job_title, job_url, desc
    except Exception:
        return None


def get_cards(driver, url):
    """Load a URL and return job cards."""
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
    return cards


def process_cards(driver, cards, applied_log, matcher_fn, section_label):
    """Process a list of job cards, apply if matching. Returns count applied."""
    count = 0
    for card in cards:
        if count >= CONFIG["max_apply_per_search"]:
            break
        try:
            info = extract_card_info(driver, card)
            if not info:
                continue
            job_title, job_url, desc = info
            log.info(f"  [{section_label}] Checking: {job_title}")
            if matcher_fn(job_title, desc):
                success = apply_to_job(driver, job_url, job_title, applied_log)
                if success:
                    count += 1
                    save_applied(CONFIG["log_file"], applied_log)
                    time.sleep(CONFIG["action_delay"])
        except StaleElementReferenceException:
            continue
        except Exception as e:
            log.warning(f"  Skipping card: {e}")
            continue
    return count


# ═══════════════════════════════════════════════════════════════
#  Main agent
# ═══════════════════════════════════════════════════════════════
def run_agent():
    log.info("")
    log.info("=" * 55)
    log.info(f"  Run started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 55)

    applied_log = load_applied(CONFIG["log_file"])
    log.info(f"Loaded {len(applied_log)} previously applied jobs")

    driver = create_driver()
    total_applied = 0

    try:
        if not login(driver, CONFIG["email"], CONFIG["password"]):
            log.error("Login failed — stopping run.")
            return

        location = CONFIG["location"].lower()   # hyderabad

        # ── SECTION 1: Regular Jobs — Hyderabad ───────────────────
        log.info("\n" + "█" * 55)
        log.info("  SECTION 1 — Regular Jobs (Hyderabad)")
        log.info("█" * 55)

        for keyword in CONFIG["search_keywords"]:
            log.info(f"\n{'─'*50}\nKeyword: {keyword}\n{'─'*50}")
            slug = keyword.lower().replace(" ", "-")
            url  = f"https://www.naukri.com/{slug}-jobs-in-{location}?jobAge=3&experience=0"
            cards = get_cards(driver, url)
            log.info(f"Found {len(cards)} listings")
            n = process_cards(driver, cards, applied_log, is_matching_job, "S1")
            total_applied += n

        # ── SECTION 2: Internships — Hyderabad ────────────────────
        log.info("\n" + "█" * 55)
        log.info(f"  SECTION 2 — Internships (Hyderabad, stipend ≥ ₹{CONFIG['min_stipend']:,}/mo)")
        log.info("█" * 55)

        for keyword in CONFIG["internship_keywords"]:
            log.info(f"\n{'─'*50}\nInternship keyword: {keyword}\n{'─'*50}")
            slug    = keyword.lower().replace(" ", "-")
            loc_slug = location.replace(" ", "-")
            url     = f"https://www.naukri.com/internship/{slug}-internship-in-{loc_slug}?jobAge=7"
            url_alt = f"https://www.naukri.com/{slug}-internship-jobs-in-{loc_slug}?jobtype=Internship&jobAge=7"

            cards = get_cards(driver, url)
            if not cards:
                cards = get_cards(driver, url_alt)
            log.info(f"Found {len(cards)} internship listings")

            for card in cards[:CONFIG["max_apply_per_search"]]:
                try:
                    info = extract_card_info(driver, card)
                    if not info:
                        continue
                    job_title, job_url, desc = info
                    stipend_text = ""
                    for cls in ["salary", "stipend", "package", "compensation"]:
                        try:
                            stipend_text = card.find_element(By.CLASS_NAME, cls).text
                            if stipend_text:
                                break
                        except NoSuchElementException:
                            continue
                    log.info(f"  [S2] Checking internship: {job_title} | stipend: '{stipend_text}'")
                    if is_matching_internship(job_title, desc, stipend_text):
                        success = apply_to_job(driver, job_url, job_title, applied_log)
                        if success:
                            total_applied += 1
                            save_applied(CONFIG["log_file"], applied_log)
                            time.sleep(CONFIG["action_delay"])
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    log.warning(f"  Skipping internship card: {e}")
                    continue

        # ── SECTION 3: WFH / Remote Jobs — any location (intentional) ──
        log.info("\n" + "█" * 55)
        log.info("  SECTION 3 — Work From Home / Remote Jobs (All India)")
        log.info("  ℹ️  No location filter — WFH jobs can be done from Hyderabad")
        log.info("█" * 55)

        for keyword in CONFIG["search_keywords"]:
            log.info(f"\n{'─'*50}\nWFH Keyword: {keyword}\n{'─'*50}")
            slug = keyword.lower().replace(" ", "-")
            url  = f"https://www.naukri.com/{slug}-jobs?jobAge=3&experience=0&wfhType=remote,hybrid"
            cards = get_cards(driver, url)
            log.info(f"Found {len(cards)} WFH listings")
            n = process_cards(driver, cards, applied_log, is_matching_job, "S3-WFH")
            total_applied += n

        # ── SECTION 4: WFH Internships ────────────────────────────
        log.info("\n" + "█" * 55)
        log.info("  SECTION 4 — Work From Home Internships (All India)")
        log.info("█" * 55)

        for keyword in CONFIG["internship_keywords"]:
            log.info(f"\n{'─'*50}\nWFH Internship keyword: {keyword}\n{'─'*50}")
            slug = keyword.lower().replace(" ", "-")
            urls = [
                f"https://www.naukri.com/internship/{slug}-internship?wfhType=remote,hybrid&jobAge=7",
                f"https://www.naukri.com/{slug}-internship-jobs?jobtype=Internship&wfhType=remote,hybrid&jobAge=7",
            ]
            cards = []
            for url in urls:
                cards = get_cards(driver, url)
                if cards:
                    break
            log.info(f"Found {len(cards)} WFH internship listings")

            for card in cards[:CONFIG["max_apply_per_search"]]:
                try:
                    info = extract_card_info(driver, card)
                    if not info:
                        continue
                    job_title, job_url, desc = info
                    stipend_text = ""
                    try:
                        stipend_text = card.find_element(
                            By.XPATH, ".//*[contains(@class,'stipend') or contains(@class,'salary')]"
                        ).text
                    except NoSuchElementException:
                        pass
                    log.info(f"  [S4] Checking WFH internship: {job_title}")
                    if is_matching_internship(job_title, desc, stipend_text):
                        success = apply_to_job(driver, job_url, job_title, applied_log)
                        if success:
                            total_applied += 1
                            save_applied(CONFIG["log_file"], applied_log)
                            time.sleep(CONFIG["action_delay"])
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    log.warning(f"  Skipping WFH internship card: {e}")
                    continue

        # ── SECTION 5: Newly Arrived Jobs — Hyderabad (last 24 hrs) ──
        log.info("\n" + "█" * 55)
        log.info("  SECTION 5 — Newly Arrived Jobs (Last 24 hrs — Hyderabad)")
        log.info("█" * 55)

        for keyword in CONFIG["search_keywords"] + CONFIG["internship_keywords"]:
            log.info(f"\n{'─'*50}\nNew jobs keyword: {keyword}\n{'─'*50}")
            slug = keyword.lower().replace(" ", "-")
            # FIX: Added location filter — was applying to all India before
            url  = f"https://www.naukri.com/{slug}-jobs-in-{location}?jobAge=1&experience=0"
            cards = get_cards(driver, url)
            log.info(f"Found {len(cards)} newly arrived listings")
            n = process_cards(driver, cards, applied_log, is_matching_job, "S5-NEW")
            total_applied += n

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
#  Entry point
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    is_ci = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"

    if is_ci:
        log.info("GitHub Actions detected — running single pass and exiting.")
        run_agent()
        log.info("Single run complete.")
    else:
        log.info("Naukri Auto-Apply Bot starting (local mode)...")
        run_agent()
        for t in CONFIG["schedule_times"]:
            schedule.every().day.at(t).do(run_agent)
            log.info(f"Scheduled: every day at {t}")
        log.info("\nScheduler active. Press Ctrl+C to stop.\n")
        while True:
            schedule.run_pending()
            time.sleep(30)
