"""
Naukri Auto-Apply Bot  v2.0  —  CLEAN REWRITE
===============================================
Sections:
  0 — Newly Arrived (last 24 hrs) — all keywords
  1 — Hyderabad Jobs              (jobAge=1)
  2 — Hyderabad Internships       (jobAge=1)
  3 — Remote / WFH Jobs           (jobAge=1)
  4 — Remote / WFH Internships    (jobAge=1)

Features:
  Cookie login  (fallback: email + password)
  Daily name alternation  (Pulabala Nagarjuna / Nagarjuna Pulabala)
  Skill + location filter before applying
  Save redirected jobs to Naukri Saved Jobs
  Duplicate prevention  (applied_jobs.json)
  Headless Chrome for GitHub Actions
  Full logging  (console + naukri_bot.log)
"""

# ── Imports ───────────────────────────────────────────────────
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException,
    ElementClickInterceptedException, StaleElementReferenceException
)
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime, date
import re, time, logging, json, os, schedule


# ══════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════
CONFIG = {
    # ── Credentials ──────────────────────────────────────────
    "email":    os.getenv("NAUKRI_EMAIL",    "your_email@example.com"),
    "password": os.getenv("NAUKRI_PASSWORD", "your_password"),
    "cookies":  os.getenv("NAUKRI_COOKIES",  ""),   # JSON string of cookies

    # ── Profile name alternation ──────────────────────────────
    "name_odd":  "Pulabala Nagarjuna",
    "name_even": "Nagarjuna Pulabala",

    # ── Locations ─────────────────────────────────────────────
    "location": "Hyderabad",

    # ── Job keywords ─────────────────────────────────────────
    "job_keywords": [
        "Java Developer",
        "Python Developer",
        "SQL Developer",
        "Software Engineer",
        "Associate Software Engineer",
        "Data Analyst",
        "AI ML Engineer",
        "Machine Learning Engineer",
    ],

    # ── Internship keywords ───────────────────────────────────
    "internship_keywords": [
        "Java Intern",
        "Python Intern",
        "SQL Intern",
        "AIML Intern",
        "Data Analyst Intern",
        "Software Engineer Intern",
    ],

    # ── Required skills (any one match = eligible) ────────────
    "required_skills": [
        "java", "python", "sql", "mysql", "postgresql",
        "software engineer", "associate software engineer",
        "customer software engineer", "software developer",
        "java developer", "python developer", "sql developer",
        "junior developer",
        "langchain", "rag", "huggingface", "faiss", "streamlit",
        "machine learning", "deep learning",
        "artificial intelligence", "natural language processing", "nlp",
        "data analyst", "data science",
        "it fresher", "software fresher", "tech fresher",
        "it trainee", "software trainee", "developer trainee",
        "it intern", "software intern", "developer intern",
        "computer science", "information technology",
    ],

    # ── Exclude keywords (title match = skip) ─────────────────
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
        "site engineer", "site supervisor",
        "electronics engineer", "embedded engineer",
        "production engineer", "manufacturing engineer",
        "automobile engineer", "aeronautical engineer",
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
        "chemical engineer", "biotech", "biotechnology",
        "automobile", "automotive", "instrumentation",
        "mechanical", "electrical maintenance", "plumber",
        "welding", "fitter", "quality control",
        "embedded", "vlsi", "iot engineer",
    ],

    # ── Internship stipend filter ─────────────────────────────
    "min_stipend": 10000,   # Rs/month — skip below this

    # ── Form answers ──────────────────────────────────────────
    "current_ctc":        "3",
    "expected_ctc":       "3",
    "notice_period_days": 15,
    "cover_letter":       None,

    # ── Run settings ─────────────────────────────────────────
    "max_apply_per_search": 10,
    "action_delay":          2,
    "log_file":   "applied_jobs.json",
    "manual_log": "manual_apply_jobs.json",
    "headless":   False,
}


# ══════════════════════════════════════════════════════════════
#  Logging
# ══════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("naukri_bot.log"),
    ],
)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
#  Applied-jobs tracker
# ══════════════════════════════════════════════════════════════
def load_applied(path):
    if os.path.exists(path):
        try:
            content = open(path).read().strip()
            return json.loads(content) if content else {}
        except (json.JSONDecodeError, ValueError):
            log.warning("[load] %s corrupt — starting fresh", path)
    return {}


def save_applied(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def save_manual_job(job_url, job_title, reason):
    """Log jobs that redirected externally (Hyderabad only)."""
    path = CONFIG["manual_log"]
    try:
        log_data = load_applied(path)
        if job_url not in log_data:
            log_data[job_url] = {
                "title":    job_title,
                "reason":   reason,
                "saved_at": datetime.now().isoformat(),
            }
            save_applied(path, log_data)
            log.info("  📌 Saved to manual log (%s): %s", reason, job_title)
    except Exception as e:
        log.warning("  Could not save manual job: %s", e)


# ══════════════════════════════════════════════════════════════
#  Browser setup
# ══════════════════════════════════════════════════════════════
def create_driver():
    options = webdriver.ChromeOptions()
    is_ci = os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("CI") == "true"

    if is_ci or CONFIG["headless"]:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--remote-debugging-port=9222")
        log.info("[driver] Headless mode")
    else:
        options.add_argument("--start-maximized")
        log.info("[driver] Visible mode")

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
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    service = Service(ChromeDriverManager().install())
    driver  = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": """
        Object.defineProperty(navigator, 'webdriver',  {get: () => undefined});
        Object.defineProperty(navigator, 'plugins',    {get: () => [1,2,3,4,5]});
        Object.defineProperty(navigator, 'languages',  {get: () => ['en-US','en']});
        Object.defineProperty(navigator, 'platform',   {get: () => 'Win32'});
        window.chrome = {runtime: {}};
    """})
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(5)
    return driver


# ══════════════════════════════════════════════════════════════
#  Popup dismisser
# ══════════════════════════════════════════════════════════════
def dismiss_popups(driver):
    XPATHS = [
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'skip')]",
        "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'skip')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'maybe later')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'not now')]",
        "//*[contains(@class,'close-btn') or contains(@class,'closeBtn') or contains(@class,'cross-btn')]",
        "//*[contains(@class,'crossIcon') or contains(@class,'cross-icon')]",
        "//*[contains(@class,'modal-close') or contains(@class,'modalClose')]",
        "//button[@aria-label='Close' or @aria-label='close' or @aria-label='Dismiss']",
        "//*[contains(@class,'overlayClose')]",
        "//*[@data-testid='modal-close']",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept')]",
        "//button[normalize-space(text())='x' or normalize-space(text())='x' or normalize-space(text())='x']",
    ]
    dismissed = 0
    for _ in range(3):
        found = False
        for xpath in XPATHS:
            try:
                for el in driver.find_elements(By.XPATH, xpath):
                    if el.is_displayed() and el.is_enabled():
                        driver.execute_script("arguments[0].click();", el)
                        time.sleep(0.5)
                        dismissed += 1
                        found = True
                        break
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


# ══════════════════════════════════════════════════════════════
#  Login — Cookie first, fallback to email/password
# ══════════════════════════════════════════════════════════════
def cookie_login(driver):
    """Try to login using saved cookies."""
    cookies_str = CONFIG["cookies"].strip()
    if not cookies_str:
        return False
    try:
        cookies = json.loads(cookies_str)
        driver.get("https://www.naukri.com")
        time.sleep(3)
        for cookie in cookies:
            try:
                cookie.pop("sameSite", None)
                driver.add_cookie(cookie)
            except Exception:
                pass
        driver.refresh()
        time.sleep(4)
        dismiss_popups(driver)
        if "naukri.com" in driver.current_url and "login" not in driver.current_url:
            log.info("Cookie login successful!")
            return True
    except Exception as e:
        log.warning("Cookie login failed: %s", e)
    return False


def email_login(driver):
    """Login with email and password."""
    log.info("Trying email/password login...")
    driver.get("https://www.naukri.com/nlogin/login")
    wait = WebDriverWait(driver, 20)
    time.sleep(5)
    try:
        email_el = wait.until(EC.element_to_be_clickable((By.ID, "usernameField")))
        email_el.click()
        time.sleep(0.4)
        email_el.clear()
        for ch in CONFIG["email"]:
            email_el.send_keys(ch)
            time.sleep(0.04)
        time.sleep(0.8)

        pwd_el = wait.until(EC.element_to_be_clickable((By.ID, "passwordField")))
        pwd_el.click()
        time.sleep(0.4)
        pwd_el.clear()
        for ch in CONFIG["password"]:
            pwd_el.send_keys(ch)
            time.sleep(0.04)
        time.sleep(0.8)

        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        time.sleep(4)
        dismiss_popups(driver)

        if "login" not in driver.current_url:
            log.info("Email login successful!")
            return True
        log.error("Email login failed — check credentials!")
        return False
    except Exception as e:
        log.error("Email login error: %s", e)
        return False


def login(driver):
    if cookie_login(driver):
        return True
    return email_login(driver)


# ══════════════════════════════════════════════════════════════
#  Skill & location filter
# ══════════════════════════════════════════════════════════════
def is_matching_job(title, description=""):
    t = title.lower()
    d = description.lower()
    for ex in CONFIG["exclude_keywords"]:
        if ex.lower() in t:
            log.info("  Skip (excluded '%s'): %s", ex, title)
            return False
    non_it = [
        "mechanical engineer", "electrical engineer", "electronics engineer",
        "civil engineer", "chemical engineer", "automobile engineer",
        "production engineer", "manufacturing engineer", "biotech",
        "vlsi", "embedded systems", "electrical maintenance",
    ]
    for sig in non_it:
        if sig in d:
            log.info("  Skip (non-IT signal '%s'): %s", sig, title)
            return False
    for skill in CONFIG["required_skills"]:
        if skill in t or skill in d:
            return True
    log.info("  Skip (no skill match): %s", title)
    return False


def is_valid_location(driver):
    """Read actual job page location — allow only Hyderabad or WFH/Remote."""
    ALLOWED = ["hyderabad", "work from home", "remote", "hybrid", "wfh", "telangana"]
    try:
        loc_xpaths = [
            "//*[contains(@class,'location')]",
            "//*[contains(@class,'loc')]",
            "//*[@data-qa='job-location']",
            "//*[contains(@class,'job-loc')]",
        ]
        for xp in loc_xpaths:
            for el in driver.find_elements(By.XPATH, xp):
                loc = el.text.strip().lower()
                if not loc:
                    continue
                if any(a in loc for a in ALLOWED):
                    log.info("  Location OK: %s", el.text.strip())
                    return True
                if len(loc) > 2:
                    log.info("  Location SKIP: %s", el.text.strip())
                    return False
    except Exception:
        pass
    return True   # allow if can't read


def extract_stipend(text):
    if not text:
        return 0
    t = text.lower().replace(",", "").replace("₹", "").replace("inr", "").strip()
    if "unpaid" in t:
        return 0
    m = re.search(r"(\d+(?:\.\d+)?)\s*k", t)
    if m:
        return int(float(m.group(1)) * 1000)
    nums = re.findall(r"\d+", t)
    if nums:
        val = int(nums[0])
        if "lpa" in t or "per annum" in t:
            return int(val * 100000 / 12)
        return val
    return 0


def is_matching_internship(title, description, stipend_text):
    if not is_matching_job(title, description):
        return False
    stipend = extract_stipend(stipend_text)
    if stipend < CONFIG["min_stipend"]:
        log.info("  Skip internship (stipend Rs%d < Rs%d): %s",
                 stipend, CONFIG["min_stipend"], title)
        return False
    return True


# ══════════════════════════════════════════════════════════════
#  Application form handler
# ══════════════════════════════════════════════════════════════
def _fill_text(driver, el, value):
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


def _best_notice_option(select_el, days):
    sel    = Select(select_el)
    parsed = []
    for opt in sel.options:
        txt = opt.text.strip().lower()
        if not txt or txt in ("select", "choose", "--"):
            continue
        if "immediate" in txt or txt == "0":
            parsed.append((0, opt.text.strip()))
        else:
            m = re.search(r"\d+", txt)
            if m:
                parsed.append((int(m.group()), opt.text.strip()))
    if not parsed:
        return None
    best = None
    for num, text in sorted(parsed, key=lambda x: x[0]):
        if num <= days:
            best = text
    return best or sorted(parsed, key=lambda x: x[0])[0][1]


def handle_application_form(driver):
    CTC_CUR  = ["current ctc", "current salary", "current package", "present ctc"]
    CTC_EXP  = ["expected ctc", "expected salary", "expected package", "desired ctc"]
    NOTICE   = ["notice period", "notice", "joining period", "available to join"]
    COVER    = ["cover letter", "cover note", "message to recruiter", "write something"]
    SKIP_COV = "No cover letter available at this time."

    for _ in range(6):
        dismiss_popups(driver)
        time.sleep(0.8)
        if not driver.find_elements(By.XPATH,
            "//form | //div[contains(@class,'modal')] | //div[contains(@class,'apply')]"):
            break

        inputs = driver.find_elements(By.XPATH,
            "//input[not(@type='hidden') and not(@type='submit') "
            "and not(@type='checkbox') and not(@type='radio') and not(@type='file')] "
            "| //textarea | //select"
        )
        for el in inputs:
            try:
                if not el.is_displayed() or not el.is_enabled():
                    continue
                tag = el.tag_name.lower()
                lbl = ""
                fid = el.get_attribute("id") or ""
                if fid:
                    try:
                        lbl = driver.find_element(
                            By.XPATH, "//label[@for='" + fid + "']"
                        ).text.strip().lower()
                    except NoSuchElementException:
                        pass
                if not lbl:
                    lbl = (el.get_attribute("placeholder") or "").lower()
                if not lbl:
                    lbl = (el.get_attribute("aria-label") or "").lower()

                if any(k in lbl for k in CTC_CUR) and tag == "input":
                    _fill_text(driver, el, CONFIG["current_ctc"])
                elif any(k in lbl for k in CTC_EXP) and tag == "input":
                    _fill_text(driver, el, CONFIG["expected_ctc"])
                elif any(k in lbl for k in NOTICE) and tag == "select":
                    best = _best_notice_option(el, CONFIG["notice_period_days"])
                    if best:
                        Select(el).select_by_visible_text(best)
                elif any(k in lbl for k in NOTICE) and tag == "input":
                    _fill_text(driver, el, str(CONFIG["notice_period_days"]))
                elif any(k in lbl for k in COVER) and tag == "textarea":
                    _fill_text(driver, el, CONFIG["cover_letter"] or SKIP_COV)
            except StaleElementReferenceException:
                continue
            except Exception:
                continue

        clicked = False
        for xp in [
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'apply now')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'apply')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
        ]:
            try:
                btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, xp)))
                driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", btn)
                clicked = True
                time.sleep(1.5)
                dismiss_popups(driver)
                break
            except (TimeoutException, Exception):
                continue
        if not clicked:
            break


# ══════════════════════════════════════════════════════════════
#  Save job on Naukri (when redirected externally)
# ══════════════════════════════════════════════════════════════
def save_on_naukri(driver, job_url, job_title, original_window):
    """Click the Naukri Save button so job appears in Saved Jobs."""
    try:
        driver.execute_script("window.open('" + job_url + "', '_blank');")
        driver.switch_to.window(driver.window_handles[-1])
        time.sleep(3)
        dismiss_popups(driver)
        SAVE_XPATHS = [
            "//button[contains(text(),'Save')]",
            "//a[contains(text(),'Save')]",
            "//*[contains(@class,'save-job')]",
            "//*[contains(@class,'saveJob')]",
            "//*[@title='Save Job']",
            "//span[contains(text(),'Save')]",
        ]
        for xp in SAVE_XPATHS:
            try:
                btn = WebDriverWait(driver, 4).until(
                    EC.element_to_be_clickable((By.XPATH, xp))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", btn)
                log.info("  💾 Saved on Naukri: %s", job_title)
                break
            except TimeoutException:
                continue
    except Exception as e:
        log.warning("  Could not save on Naukri: %s", e)
    finally:
        try:
            driver.close()
            driver.switch_to.window(original_window)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
#  Apply to a single job
# ══════════════════════════════════════════════════════════════
def apply_to_job(driver, job_url, job_title, applied_log, is_hyderabad=True):
    """
    Open job, check location + skills, apply.
    is_hyderabad=True  → save redirected jobs on Naukri + manual log
    is_hyderabad=False → skip redirected jobs silently (WFH section)
    """
    if job_url in applied_log:
        log.info("  Already applied: %s", job_title)
        return False

    original_window = driver.current_window_handle
    driver.execute_script("window.open('" + job_url + "', '_blank');")
    driver.switch_to.window(driver.window_handles[-1])
    time.sleep(CONFIG["action_delay"])

    try:
        dismiss_popups(driver)

        # Location check
        if not is_valid_location(driver):
            log.info("  Skip (wrong location): %s", job_title)
            driver.close()
            driver.switch_to.window(original_window)
            return False

        # Full-page skill check
        try:
            full_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        except Exception:
            full_text = job_title.lower()

        if not any(s in full_text for s in CONFIG["required_skills"]):
            log.info("  Skip (no skill on page): %s", job_title)
            driver.close()
            driver.switch_to.window(original_window)
            return False
        if any(ex in job_title.lower() for ex in CONFIG["exclude_keywords"]):
            log.info("  Skip (excluded): %s", job_title)
            driver.close()
            driver.switch_to.window(original_window)
            return False

        # Save on Naukri first (before Apply click)
        try:
            for sv_xp in [
                "//button[contains(text(),'Save')]",
                "//a[contains(text(),'Save')]",
                "//*[contains(@class,'save-job')]",
                "//*[contains(@class,'saveJob')]",
            ]:
                els = driver.find_elements(By.XPATH, sv_xp)
                for el in els:
                    if el.is_displayed():
                        driver.execute_script("arguments[0].click();", el)
                        time.sleep(0.5)
                        break
        except Exception:
            pass

        # Find Apply button
        wait = WebDriverWait(driver, 10)
        apply_btn = None
        for xp in [
            "//button[contains(text(),'Apply')]",
            "//a[contains(text(),'Apply')]",
            "//button[@id='apply-button']",
            "//*[contains(@class,'apply-button')]",
            "//button[contains(@class,'applyBtn')]",
        ]:
            try:
                apply_btn = wait.until(EC.element_to_be_clickable((By.XPATH, xp)))
                break
            except TimeoutException:
                continue

        if not apply_btn:
            log.info("  Skip (no Apply button): %s", job_title)
            driver.close()
            driver.switch_to.window(original_window)
            return False

        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", apply_btn)
        time.sleep(0.8)
        dismiss_popups(driver)
        try:
            apply_btn.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", apply_btn)
        log.info("  Clicked Apply: %s", job_title)
        time.sleep(1.5)

        # Check for external redirect
        pg = driver.page_source.lower()
        cur = driver.current_url.lower()
        external_kw = [
            "apply on company website", "apply via company", "external application",
            "apply via email", "send your resume", "email your cv",
            "apply via whatsapp", "whatsapp to apply",
        ]
        is_external = any(k in pg for k in external_kw)
        if not is_external and "naukri.com" not in cur:
            is_external = True

        if is_external:
            if is_hyderabad:
                save_manual_job(job_url, job_title, "external_redirect")
                driver.close()
                driver.switch_to.window(original_window)
                save_on_naukri(driver, job_url, job_title, original_window)
            else:
                log.info("  Skip (external redirect — WFH): %s", job_title)
                driver.close()
                driver.switch_to.window(original_window)
            return False

        # Fill form
        dismiss_popups(driver)
        handle_application_form(driver)

        log.info("  Applied: %s", job_title)
        applied_log[job_url] = {
            "title":      job_title,
            "applied_at": datetime.now().isoformat(),
            "url":        job_url,
        }
        driver.close()
        driver.switch_to.window(original_window)
        return True

    except ElementClickInterceptedException:
        log.info("  Skip (click blocked): %s", job_title)
    except Exception as e:
        log.warning("  Error on %s: %s", job_title, str(e)[:80])
    try:
        driver.close()
        driver.switch_to.window(original_window)
    except Exception:
        pass
    return False


# ══════════════════════════════════════════════════════════════
#  Job card helpers
# ══════════════════════════════════════════════════════════════
def get_cards(driver, url):
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


def card_info(driver, card):
    try:
        try:
            title_el = card.find_element(By.CLASS_NAME, "title")
        except NoSuchElementException:
            title_el = card.find_element(By.TAG_NAME, "a")
        title = title_el.text.strip()
        url   = title_el.get_attribute("href") or card.find_element(By.TAG_NAME, "a").get_attribute("href")
        if not title or not url:
            return None
        try:
            desc = card.find_element(By.CLASS_NAME, "job-description").text
        except NoSuchElementException:
            try:
                desc = card.find_element(By.CLASS_NAME, "job-desc").text
            except NoSuchElementException:
                desc = ""
        return title, url, desc
    except Exception:
        return None


def process_cards(driver, cards, applied_log, is_hyderabad=True, label=""):
    count = 0
    for card in cards:
        if count >= CONFIG["max_apply_per_search"]:
            break
        try:
            info = card_info(driver, card)
            if not info:
                continue
            title, url, desc = info
            log.info("  [%s] Checking: %s", label, title)
            if is_matching_job(title, desc):
                ok = apply_to_job(driver, url, title, applied_log, is_hyderabad)
                if ok:
                    count += 1
                    save_applied(CONFIG["log_file"], applied_log)
                    time.sleep(CONFIG["action_delay"])
        except StaleElementReferenceException:
            continue
        except Exception as e:
            log.warning("  Card error: %s", e)
            continue
    return count


def process_internship_cards(driver, cards, applied_log, is_hyderabad=True, label=""):
    count = 0
    for card in cards:
        if count >= CONFIG["max_apply_per_search"]:
            break
        try:
            info = card_info(driver, card)
            if not info:
                continue
            title, url, desc = info
            stipend = ""
            for cls in ["salary", "stipend", "package"]:
                try:
                    stipend = card.find_element(By.CLASS_NAME, cls).text
                    if stipend:
                        break
                except NoSuchElementException:
                    continue
            log.info("  [%s] Checking internship: %s | stipend: %s", label, title, stipend)
            if is_matching_internship(title, desc, stipend):
                ok = apply_to_job(driver, url, title, applied_log, is_hyderabad)
                if ok:
                    count += 1
                    save_applied(CONFIG["log_file"], applied_log)
                    time.sleep(CONFIG["action_delay"])
        except StaleElementReferenceException:
            continue
        except Exception as e:
            log.warning("  Internship card error: %s", e)
            continue
    return count


# ══════════════════════════════════════════════════════════════
#  Daily name update
# ══════════════════════════════════════════════════════════════
def daily_name_update(driver):
    FLAG = "profile_updated_date.txt"
    today = str(date.today())
    if os.path.exists(FLAG) and open(FLAG).read().strip() == today:
        log.info("[profile] Already updated today — skipping")
        return

    log.info("\n" + "─" * 55)
    log.info("  DAILY PROFILE UPDATE — Name alternation")
    log.info("─" * 55)

    try:
        day_num   = date.today().toordinal()
        name_today = CONFIG["name_odd"] if day_num % 2 == 1 else CONFIG["name_even"]
        log.info("  Today's name (%s day): %s",
                 "odd" if day_num % 2 == 1 else "even", name_today)

        driver.get("https://www.naukri.com/mnjuser/profile?id=&altresid")
        time.sleep(8)
        dismiss_popups(driver)
        time.sleep(2)

        # Log all clickable edit elements for debugging
        found_els = driver.execute_script("""
            var res = [];
            ['button','span','i','a','div'].forEach(function(t){
                var els = document.getElementsByTagName(t);
                for(var i=0;i<els.length;i++){
                    var e=els[i];
                    var cls=e.getAttribute('class')||'';
                    var title=e.getAttribute('title')||'';
                    var aria=e.getAttribute('aria-label')||'';
                    var ga=e.getAttribute('data-ga-track')||'';
                    var r=e.getBoundingClientRect();
                    if(r.width>0&&r.height>0&&(
                        title.toLowerCase().includes('edit')||
                        aria.toLowerCase().includes('edit')||
                        ga.toLowerCase().includes('edit')||
                        cls.toLowerCase().includes('pencil')||
                        cls.toLowerCase().includes('naukicon')||
                        cls.toLowerCase().includes('edit'))){
                        res.push(t+'|'+cls+'|'+title+'|'+aria+'|'+ga);
                    }
                }
            });
            return res.slice(0,10);
        """)
        log.info("  Edit elements found: %s", found_els)

        # Force all edit elements visible
        driver.execute_script("""
            var els=document.querySelectorAll('[class*="edit"],[class*="Edit"],[title*="edit"],[title*="Edit"]');
            for(var i=0;i<els.length;i++){
                els[i].style.display='block';
                els[i].style.visibility='visible';
                els[i].style.opacity='1';
                els[i].style.pointerEvents='auto';
            }
        """)
        time.sleep(0.5)

        # Try every possible edit selector
        EDIT_SELECTORS = [
            "//*[@title='Edit']",
            "//*[@title='edit']",
            "//*[contains(@title,'Edit')]",
            "//*[contains(@aria-label,'edit') or contains(@aria-label,'Edit')]",
            "//*[contains(@data-ga-track,'edit') or contains(@data-ga-track,'Edit')]",
            "//*[contains(@data-ga-track,'Basic') or contains(@data-ga-track,'basic')]",
            "//*[contains(@class,'naukicon-edit')]",
            "//*[contains(@class,'icon-edit')]",
            "//*[contains(@class,'pencil')]",
            "//*[contains(@class,'editContainer')]",
            "//*[contains(@class,'profileEditIcon')]",
            "//button[.//svg]",
            "//span[.//svg]",
            "(//*[contains(@class,'edit')])[1]",
            "(//span[contains(@class,'icon')])[1]",
            "(//button)[1]",
        ]

        name_clicked = False
        for sel in EDIT_SELECTORS:
            try:
                for el in driver.find_elements(By.XPATH, sel)[:3]:
                    try:
                        driver.execute_script(
                            "arguments[0].style.display='block';"
                            "arguments[0].style.visibility='visible';"
                            "arguments[0].style.pointerEvents='auto';", el
                        )
                        time.sleep(0.3)
                        driver.execute_script("arguments[0].click();", el)
                        time.sleep(2)
                        # Check if name input appeared
                        name_inputs = driver.find_elements(By.XPATH,
                            "//input[contains(translate(@placeholder,"
                            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'name') "
                            "or @name='fullName' or @id='fullName' or @name='name' or @id='name']"
                        )
                        if name_inputs:
                            name_clicked = True
                            log.info("  Opened name editor via: %s", sel[:60])
                            break
                        dismiss_popups(driver)
                    except Exception:
                        continue
                if name_clicked:
                    break
            except Exception:
                continue

        if name_clicked:
            NAME_INPUTS = [
                "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'name')]",
                "//input[@name='fullName']",
                "//input[@id='fullName']",
                "//input[@name='name']",
                "//input[@id='name']",
                "//input[@type='text'][1]",
            ]
            name_field = None
            for sel in NAME_INPUTS:
                for el in driver.find_elements(By.XPATH, sel):
                    if el.is_displayed() and el.is_enabled():
                        name_field = el
                        break
                if name_field:
                    break

            if name_field:
                name_field.click()
                name_field.send_keys(Keys.CONTROL + "a")
                name_field.clear()
                time.sleep(0.3)
                name_field.send_keys(name_today)
                time.sleep(0.5)
                log.info("  Typed name: %s", name_today)

                for sv_xp in [
                    "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]",
                    "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'update')]",
                    "//button[@type='submit']",
                ]:
                    try:
                        btn = WebDriverWait(driver, 4).until(
                            EC.element_to_be_clickable((By.XPATH, sv_xp))
                        )
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(2)
                        log.info("  Name updated to: %s", name_today)
                        with open(FLAG, "w") as f:
                            f.write(today)
                        break
                    except TimeoutException:
                        continue
            else:
                log.warning("  Could not find name input field")
        else:
            log.warning("  Could not find name edit button. Elements: %s", found_els)

    except Exception as e:
        log.warning("  Name update failed (non-critical): %s", e)


# ══════════════════════════════════════════════════════════════
#  Main agent
# ══════════════════════════════════════════════════════════════
def run_agent():
    log.info("\n" + "=" * 55)
    log.info("  Run started: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 55)

    applied_log = load_applied(CONFIG["log_file"])
    log.info("Previously applied: %d jobs", len(applied_log))

    driver = create_driver()
    total  = 0

    try:
        # ── Login ─────────────────────────────────────────────
        if not login(driver):
            log.error("Login failed — stopping.")
            return

        # ── Daily name update ─────────────────────────────────
        daily_name_update(driver)

        loc  = CONFIG["location"].lower()   # hyderabad
        kws  = CONFIG["job_keywords"]
        ikws = CONFIG["internship_keywords"]

        # ══ SECTION 0 — Newly Arrived (last 24 hrs, all keywords) ══
        log.info("\n" + "█" * 55)
        log.info("  SECTION 0 — Newly Arrived Jobs & Internships (24 hrs)")
        log.info("█" * 55)
        for kw in kws + ikws:
            slug = kw.lower().replace(" ", "-")
            for url in [
                "https://www.naukri.com/" + slug + "-jobs-in-" + loc + "?jobAge=1&experience=0",
                "https://www.naukri.com/" + slug + "-jobs?jobAge=1&experience=0&wfhType=remote,hybrid",
            ]:
                cards = get_cards(driver, url)
                log.info("  New listing '%s': %d cards", kw, len(cards))
                total += process_cards(driver, cards, applied_log,
                                       is_hyderabad=("in-" + loc in url), label="S0")

        # ══ SECTION 1 — Hyderabad Jobs ════════════════════════
        log.info("\n" + "█" * 55)
        log.info("  SECTION 1 — Hyderabad Jobs (jobAge=1)")
        log.info("█" * 55)
        for kw in kws:
            slug  = kw.lower().replace(" ", "-")
            url   = "https://www.naukri.com/" + slug + "-jobs-in-" + loc + "?jobAge=1&experience=0"
            cards = get_cards(driver, url)
            log.info("  [S1] '%s': %d cards", kw, len(cards))
            total += process_cards(driver, cards, applied_log,
                                   is_hyderabad=True, label="S1")

        # ══ SECTION 2 — Hyderabad Internships ═════════════════
        log.info("\n" + "█" * 55)
        log.info("  SECTION 2 — Hyderabad Internships (jobAge=1)")
        log.info("█" * 55)
        for kw in ikws:
            slug     = kw.lower().replace(" ", "-")
            loc_slug = loc.replace(" ", "-")
            url      = "https://www.naukri.com/internship/" + slug + "-internship-in-" + loc_slug + "?jobAge=1"
            url_alt  = "https://www.naukri.com/" + slug + "-internship-jobs-in-" + loc_slug + "?jobtype=Internship&jobAge=1"
            cards    = get_cards(driver, url)
            if not cards:
                cards = get_cards(driver, url_alt)
            log.info("  [S2] '%s': %d cards", kw, len(cards))
            total += process_internship_cards(driver, cards, applied_log,
                                              is_hyderabad=True, label="S2")

        # ══ SECTION 3 — Remote/WFH Jobs ═══════════════════════
        log.info("\n" + "█" * 55)
        log.info("  SECTION 3 — Remote / WFH Jobs (jobAge=1)")
        log.info("█" * 55)
        for kw in kws:
            slug  = kw.lower().replace(" ", "-")
            url   = "https://www.naukri.com/" + slug + "-jobs?jobAge=1&experience=0&wfhType=remote,hybrid"
            cards = get_cards(driver, url)
            log.info("  [S3] '%s': %d cards", kw, len(cards))
            total += process_cards(driver, cards, applied_log,
                                   is_hyderabad=False, label="S3")

        # ══ SECTION 4 — Remote/WFH Internships ════════════════
        log.info("\n" + "█" * 55)
        log.info("  SECTION 4 — Remote / WFH Internships (jobAge=1)")
        log.info("█" * 55)
        for kw in ikws:
            slug = kw.lower().replace(" ", "-")
            cards = []
            for url in [
                "https://www.naukri.com/internship/" + slug + "-internship?wfhType=remote,hybrid&jobAge=1",
                "https://www.naukri.com/" + slug + "-internship-jobs?jobtype=Internship&wfhType=remote,hybrid&jobAge=1",
            ]:
                cards = get_cards(driver, url)
                if cards:
                    break
            log.info("  [S4] '%s': %d cards", kw, len(cards))
            total += process_internship_cards(driver, cards, applied_log,
                                              is_hyderabad=False, label="S4")

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    log.info("\n" + "=" * 55)
    log.info("  Run complete — Applied this session: %d", total)
    log.info("  Total ever applied: %d", len(load_applied(CONFIG["log_file"])))
    log.info("=" * 55)


# ══════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    is_ci = os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("CI") == "true"
    if is_ci:
        log.info("GitHub Actions — single run")
        run_agent()
    else:
        log.info("Local mode — running now then scheduling every 4 hrs")
        run_agent()
        schedule.every(4).hours.do(run_agent)
        while True:
            schedule.run_pending()
            time.sleep(60)
