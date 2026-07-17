"""
Naukri Auto-Apply Bot  v2.0  —  Clean Rewrite
===============================================
Sections:
  Section 0  — Newly arrived jobs & internships (last 24 hrs, Hyderabad + WFH)
  Section 1  — Hyderabad jobs        (last 24 hrs)
  Section 2  — Hyderabad internships (last 24 hrs)
  Section 3  — Remote / WFH jobs     (last 24 hrs)
  Section 4  — Remote / WFH internships (last 24 hrs)

Features:
  Cookie-based login (fast + reliable)
  Location check on actual job page (Hyderabad or WFH only)
  Full-page skill match before applying
  Non-IT job filter
  Multi-step form filler (CTC, notice period, cover letter)
  Save to Naukri Saved Jobs when job redirects externally
  Duplicate prevention via applied_jobs.json
  Daily name alternation to keep profile "recently updated"
  Runs every 4 hrs via GitHub Actions
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
import re, time, logging, json, os, schedule
from datetime import datetime, date


# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════
CONFIG = {
    # ── Login ────────────────────────────────────────────────────
    "email":    os.getenv("NAUKRI_EMAIL",    "pulabalanagarjuna07@gmail.com"),
    "password": os.getenv("NAUKRI_PASSWORD", "your_password"),

    # ── Search ───────────────────────────────────────────────────
    "location": "Hyderabad",

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

    "internship_keywords": [
        "Java Intern",
        "Python Intern",
        "SQL Intern",
        "AIML Intern",
        "Data Analyst Intern",
        "Software Engineer Intern",
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

    # ── Non-IT signals (checked on full job page) ─────────────────
    "non_it_signals": [
        "mechanical engineer", "electrical engineer", "electronics engineer",
        "civil engineer", "chemical engineer", "automobile engineer",
        "production engineer", "manufacturing engineer", "instrumentation",
        "electrical maintenance", "plumber", "fitter", "welding",
    ],

    # ── Form answers ─────────────────────────────────────────────
    "current_ctc":        "3",
    "expected_ctc":       "3",
    "notice_period_days": 15,
    "cover_letter":       None,

    # ── Internship ───────────────────────────────────────────────
    "min_stipend": 10000,

    # ── Limits ───────────────────────────────────────────────────
    "max_apply_per_search": 10,
    "action_delay":          2,

    # ── Files ────────────────────────────────────────────────────
    "applied_log":          "applied_jobs.json",
    "manual_log":           "manual_apply_jobs.json",
    "profile_flag":         "profile_updated_date.txt",
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
#  JSON helpers
# ═══════════════════════════════════════════════════════════════
def load_json(path):
    if os.path.exists(path):
        try:
            content = open(path).read().strip()
            return json.loads(content) if content else {}
        except (json.JSONDecodeError, ValueError):
            log.warning(f"  {path} was corrupt — starting fresh")
    return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ═══════════════════════════════════════════════════════════════
#  Browser setup
# ═══════════════════════════════════════════════════════════════
def create_driver():
    options = webdriver.ChromeOptions()
    is_ci = os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("CI") == "true"

    if is_ci:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        log.info("  [driver] Headless mode (GitHub Actions)")
    else:
        options.add_argument("--start-maximized")
        log.info("  [driver] Visible mode (local)")

    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-extensions")
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
        Object.defineProperty(navigator, 'plugins',    {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages',  {get: () => ['en-US', 'en']});
        Object.defineProperty(navigator, 'platform',   {get: () => 'Win32'});
        window.chrome = {runtime: {}};
    """})
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(5)
    return driver


# ═══════════════════════════════════════════════════════════════
#  Login — cookie first, fallback to email/password
# ═══════════════════════════════════════════════════════════════
def login(driver):
    cookies_raw = os.getenv("NAUKRI_COOKIES", "")

    # ── Try cookie login ──────────────────────────────────────────
    if cookies_raw:
        try:
            log.info("  Trying cookie login...")
            driver.get("https://www.naukri.com")
            time.sleep(3)
            cookies = json.loads(cookies_raw)
            log.info(f"  Loading {len(cookies)} cookies...")
            for c in cookies:
                try:
                    c.pop("sameSite", None)
                    driver.add_cookie(c)
                except Exception:
                    pass
            driver.refresh()
            time.sleep(4)
            if "naukri.com" in driver.current_url and "login" not in driver.current_url:
                log.info("  ✅ Cookie login successful!")
                return True
            log.warning("  Cookie login failed — trying email/password")
        except Exception as e:
            log.warning(f"  Cookie login error: {e}")

    # ── Fallback: email + password ────────────────────────────────
    log.info("  Trying email/password login...")
    driver.get("https://www.naukri.com/nlogin/login")
    wait = WebDriverWait(driver, 20)
    time.sleep(5)
    try:
        ef = wait.until(EC.element_to_be_clickable((By.ID, "usernameField")))
        ef.clear()
        for ch in CONFIG["email"]:
            ef.send_keys(ch)
            time.sleep(0.04)
        time.sleep(0.8)

        pf = driver.find_element(By.ID, "passwordField")
        pf.clear()
        for ch in CONFIG["password"]:
            pf.send_keys(ch)
            time.sleep(0.04)
        time.sleep(0.8)

        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        wait.until(EC.url_contains("naukri.com"))
        time.sleep(3)
        log.info("  ✅ Email/password login successful!")
        dismiss_popups(driver)
        return True
    except Exception as e:
        log.error(f"  ❌ Login failed: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
#  Popup dismisser
# ═══════════════════════════════════════════════════════════════
def dismiss_popups(driver):
    XPATHS = [
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'skip')]",
        "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'skip')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'maybe later')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'not now')]",
        "//button[normalize-space(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'))='later']",
        "//*[contains(@class,'close-btn') or contains(@class,'closeBtn') or contains(@class,'crossIcon')]",
        "//*[contains(@class,'modal-close') or contains(@class,'modalClose') or contains(@class,'overlayClose')]",
        "//button[@aria-label='Close' or @aria-label='close' or @aria-label='Dismiss']",
        "//*[@data-testid='modal-close'] | //*[@data-testid='close-button']",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept')]",
        "//button[normalize-space(text())='×' or normalize-space(text())='✕']",
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
    except Exception:
        pass
    return dismissed


# ═══════════════════════════════════════════════════════════════
#  Filters
# ═══════════════════════════════════════════════════════════════
def is_valid_location(driver):
    """Returns True only if job page shows Hyderabad or WFH/Remote."""
    ALLOWED = ["hyderabad", "work from home", "remote", "hybrid", "wfh", "telangana"]
    try:
        for sel in [
            "//*[contains(@class,'location')]",
            "//*[contains(@class,'loc')]",
            "//*[@data-qa='job-location']",
        ]:
            for el in driver.find_elements(By.XPATH, sel):
                txt = el.text.strip().lower()
                if not txt or len(txt) < 3:
                    continue
                if any(a in txt for a in ALLOWED):
                    log.info(f"  [location] ✅ {el.text.strip()}")
                    return True
                log.info(f"  [location] ❌ Wrong: {el.text.strip()} — skip")
                return False
    except Exception:
        pass
    return True  # allow if can't read location


def is_matching_job(title, page_text=""):
    """Checks required skills and exclude keywords."""
    tl = title.lower()
    pt = page_text.lower()

    # Exclude check on title
    for ex in CONFIG["exclude_keywords"]:
        if ex.lower() in tl:
            log.info(f"  [filter] Excluded '{ex}': {title}")
            return False

    # Non-IT signal on full page
    for sig in CONFIG["non_it_signals"]:
        if sig in pt:
            log.info(f"  [filter] Non-IT signal '{sig}': {title}")
            return False

    # Required skill check on title + full page
    for skill in CONFIG["required_skills"]:
        if skill.lower() in tl or skill.lower() in pt:
            return True

    log.info(f"  [filter] No skill match: {title}")
    return False


def extract_stipend(text):
    if not text:
        return 0
    t = text.lower().replace(",", "").replace("₹", "").replace("inr", "")
    if "unpaid" in t:
        return 0
    m = re.search(r"(\d+(?:\.\d+)?)\s*k", t)
    if m:
        return int(float(m.group(1)) * 1000)
    nums = re.findall(r"\d+", t)
    return int(nums[0]) if nums else 0


# ═══════════════════════════════════════════════════════════════
#  Application form handler
# ═══════════════════════════════════════════════════════════════
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


def handle_form(driver):
    CTC_CUR  = ["current ctc", "current salary", "current package", "present ctc"]
    CTC_EXP  = ["expected ctc", "expected salary", "expected package", "desired ctc"]
    NOTICE   = ["notice period", "notice", "joining period", "available to join"]
    COVER    = ["cover letter", "cover note", "message to recruiter", "write something"]
    COVER_TXT = "No cover letter available at this time."

    form_found = False
    for _ in range(6):
        dismiss_popups(driver)
        time.sleep(0.8)

        if not driver.find_elements(By.XPATH,
            "//form | //div[contains(@class,'modal')] | //div[contains(@class,'apply')]"
        ):
            break

        for el in driver.find_elements(By.XPATH,
            "//input[not(@type='hidden') and not(@type='submit') "
            "and not(@type='checkbox') and not(@type='radio') and not(@type='file')] "
            "| //textarea | //select"
        ):
            try:
                if not el.is_displayed() or not el.is_enabled():
                    continue
                tag = el.tag_name.lower()
                lbl = ""
                fid = el.get_attribute("id") or ""
                if fid:
                    try:
                        lbl = driver.find_element(By.XPATH, f"//label[@for='{fid}']").text.strip().lower()
                    except Exception:
                        pass
                if not lbl:
                    lbl = (el.get_attribute("placeholder") or "").lower()
                if not lbl:
                    lbl = (el.get_attribute("aria-label") or "").lower()

                if any(k in lbl for k in CTC_CUR) and tag == "input":
                    if _fill_text(driver, el, CONFIG["current_ctc"]):
                        form_found = True
                elif any(k in lbl for k in CTC_EXP) and tag == "input":
                    if _fill_text(driver, el, CONFIG["expected_ctc"]):
                        form_found = True
                elif any(k in lbl for k in NOTICE) and tag == "select":
                    sel = Select(el)
                    parsed = []
                    for opt in sel.options:
                        t = opt.text.strip().lower()
                        if not t or t in ("select", "choose", "--"):
                            continue
                        n = 0 if "immediate" in t else (
                            int(re.search(r"\d+", t).group()) if re.search(r"\d+", t) else None
                        )
                        if n is not None:
                            parsed.append((n, opt.text.strip()))
                    if parsed:
                        best = min(
                            [p for p in parsed if p[0] <= CONFIG["notice_period_days"]] or parsed,
                            key=lambda x: x[0]
                        )
                        Select(el).select_by_visible_text(best[1])
                        form_found = True
                elif any(k in lbl for k in COVER) and tag == "textarea":
                    _fill_text(driver, el, CONFIG["cover_letter"] or COVER_TXT)
                    form_found = True
            except StaleElementReferenceException:
                continue
            except Exception:
                continue

        # Click Next / Submit
        clicked = False
        for btn_xpath in [
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'apply')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
        ]:
            try:
                btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, btn_xpath)))
                driver.execute_script("arguments[0].click();", btn)
                clicked = True
                form_found = True
                time.sleep(1.5)
                dismiss_popups(driver)
                break
            except Exception:
                continue
        if not clicked:
            break
    return form_found


# ═══════════════════════════════════════════════════════════════
#  Save to Naukri Saved Jobs (for redirected jobs)
# ═══════════════════════════════════════════════════════════════
def save_to_manual_log(job_url, job_title, reason):
    manual = load_json(CONFIG["manual_log"])
    if job_url not in manual:
        manual[job_url] = {
            "title":    job_title,
            "reason":   reason,
            "saved_at": datetime.now().isoformat(),
        }
        save_json(CONFIG["manual_log"], manual)
        log.info(f"  📌 Saved to manual log ({reason}): {job_title}")


def click_naukri_save(driver, job_url, job_title):
    """Click the Save button on Naukri job page."""
    original = driver.current_window_handle
    try:
        driver.execute_script(f"window.open('{job_url}', '_blank');")
        driver.switch_to.window(driver.window_handles[-1])
        time.sleep(3)
        dismiss_popups(driver)

        for sel in [
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]",
            "//span[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]",
            "//*[contains(@class,'save-job') or contains(@class,'saveJob')]",
            "//*[@title='Save Job' or @title='Save job']",
        ]:
            try:
                btn = WebDriverWait(driver, 4).until(EC.element_to_be_clickable((By.XPATH, sel)))
                driver.execute_script("arguments[0].click();", btn)
                log.info(f"  💾 Saved on Naukri: {job_title}")
                time.sleep(1)
                break
            except TimeoutException:
                continue
    except Exception as e:
        log.warning(f"  Could not save on Naukri: {e}")
    finally:
        try:
            driver.close()
            driver.switch_to.window(original)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
#  Apply to a single job
# ═══════════════════════════════════════════════════════════════
def apply_to_job(driver, job_url, job_title, applied_log, save_if_redirected=False):
    if job_url in applied_log:
        log.info(f"  Already applied: {job_title}")
        return False

    original = driver.current_window_handle
    driver.execute_script(f"window.open('{job_url}', '_blank');")
    driver.switch_to.window(driver.window_handles[-1])
    time.sleep(CONFIG["action_delay"])
    wait = WebDriverWait(driver, 10)

    try:
        dismiss_popups(driver)

        # ── Location check ────────────────────────────────────────
        if not is_valid_location(driver):
            log.info(f"  Skipping (wrong location): {job_title}")
            driver.close()
            driver.switch_to.window(original)
            return False

        # ── Full page skill check ─────────────────────────────────
        try:
            page_text = driver.find_element(By.TAG_NAME, "body").text
        except Exception:
            page_text = job_title

        if not is_matching_job(job_title, page_text):
            driver.close()
            driver.switch_to.window(original)
            return False

        # ── Find Apply button ─────────────────────────────────────
        apply_btn = None
        for sel in [
            "//button[contains(text(),'Apply')]",
            "//a[contains(text(),'Apply')]",
            "//button[@id='apply-button']",
            "//*[contains(@class,'apply-button') or contains(@class,'applyBtn')]",
            "//*[@data-ga-track='Apply']",
        ]:
            try:
                apply_btn = wait.until(EC.element_to_be_clickable((By.XPATH, sel)))
                break
            except TimeoutException:
                continue

        if not apply_btn:
            log.info(f"  Skipping (no Apply button): {job_title}")
            driver.close()
            driver.switch_to.window(original)
            return False

        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", apply_btn)
        time.sleep(0.8)
        dismiss_popups(driver)
        try:
            apply_btn.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", apply_btn)
        log.info(f"  Clicked Apply: {job_title}")
        time.sleep(1.5)

        # ── Check for external redirect ───────────────────────────
        page_src = driver.page_source.lower()
        cur_url  = driver.current_url.lower()
        EXTERNAL = [
            "apply on company website", "apply via company",
            "apply via email", "send your resume", "email your cv",
            "apply via whatsapp", "whatsapp to apply",
        ]
        is_external = any(k in page_src for k in EXTERNAL)
        if not is_external and "naukri.com" not in cur_url:
            is_external = True

        if is_external:
            log.info(f"  External redirect: {job_title}")
            if save_if_redirected:
                save_to_manual_log(job_url, job_title, "external_redirect")
                driver.close()
                driver.switch_to.window(original)
                click_naukri_save(driver, job_url, job_title)
            else:
                log.info(f"  Skipping (WFH external redirect): {job_title}")
                driver.close()
                driver.switch_to.window(original)
            return False

        # ── Fill form ─────────────────────────────────────────────
        dismiss_popups(driver)
        handle_form(driver)

        log.info(f"  ✅ Applied: {job_title}")
        applied_log[job_url] = {
            "title":      job_title,
            "applied_at": datetime.now().isoformat(),
            "url":        job_url,
        }
        driver.close()
        driver.switch_to.window(original)
        return True

    except ElementClickInterceptedException:
        log.info(f"  Skipping (click blocked): {job_title}")
    except Exception as e:
        log.warning(f"  Error on {job_title}: {str(e)[:80]}")
    try:
        driver.close()
        driver.switch_to.window(original)
    except Exception:
        pass
    return False


# ═══════════════════════════════════════════════════════════════
#  Job card extractor
# ═══════════════════════════════════════════════════════════════
def get_cards(driver, url):
    driver.get(url)
    time.sleep(CONFIG["action_delay"])
    dismiss_popups(driver)
    for _ in range(3):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
    for css in [".cust-job-tuple", ".srp-jobtuple-wrapper", "[data-job-id]"]:
        cards = driver.find_elements(By.CSS_SELECTOR, css)
        if cards:
            return cards
    return []


def process_cards(driver, cards, applied_log, is_internship=False,
                  save_if_redirected=False, section_label=""):
    count = 0
    for card in cards:
        if count >= CONFIG["max_apply_per_search"]:
            break
        try:
            try:
                title_el = card.find_element(By.CLASS_NAME, "title")
            except NoSuchElementException:
                title_el = card.find_element(By.TAG_NAME, "a")
            job_title = title_el.text.strip()
            job_url   = title_el.get_attribute("href")
            if not job_title or not job_url:
                continue

            log.info(f"  [{section_label}] Checking: {job_title}")

            # Quick title filter before opening page
            if not is_matching_job(job_title):
                continue

            # Internship stipend check (from card)
            if is_internship:
                stipend_text = ""
                for cls in ["salary", "stipend", "package"]:
                    try:
                        stipend_text = card.find_element(By.CLASS_NAME, cls).text
                        if stipend_text:
                            break
                    except NoSuchElementException:
                        continue
                stipend = extract_stipend(stipend_text)
                if stipend and stipend < CONFIG["min_stipend"]:
                    log.info(f"  [{section_label}] Low stipend ₹{stipend:,}: {job_title}")
                    continue

            success = apply_to_job(
                driver, job_url, job_title, applied_log,
                save_if_redirected=save_if_redirected
            )
            if success:
                count += 1
                save_json(CONFIG["applied_log"], applied_log)
                time.sleep(CONFIG["action_delay"])

        except StaleElementReferenceException:
            continue
        except Exception as e:
            log.warning(f"  Card error: {e}")
            continue
    return count


# ═══════════════════════════════════════════════════════════════
#  Daily profile name update
# ═══════════════════════════════════════════════════════════════
def update_profile_name(driver):
    today_str = str(date.today())
    flag_file = CONFIG["profile_flag"]

    # Run only once per day
    if os.path.exists(flag_file):
        if open(flag_file).read().strip() == today_str:
            log.info("  Profile already updated today — skipping")
            return

    log.info("\n" + "─" * 55)
    log.info("  DAILY PROFILE UPDATE — Alternating name")
    log.info("─" * 55)

    is_odd = date.today().toordinal() % 2 == 1
    name_today = "Pulabala Nagarjuna" if is_odd else "Nagarjuna Pulabala"
    log.info(f"  Today's name ({'odd' if is_odd else 'even'} day): {name_today}")

    try:
        driver.get("https://www.naukri.com/mnjuser/profile?id=&altresid")
        time.sleep(8)
        dismiss_popups(driver)
        time.sleep(2)

        # Log all potential edit elements for debugging
        edit_info = driver.execute_script("""
            var res = [];
            var els = document.querySelectorAll('*');
            for(var i=0; i<els.length; i++){
                var el = els[i];
                var cls   = el.getAttribute('class') || '';
                var title = el.getAttribute('title') || '';
                var aria  = el.getAttribute('aria-label') || '';
                var dga   = el.getAttribute('data-ga-track') || '';
                var rect  = el.getBoundingClientRect();
                if(rect.width>0 && rect.height>0 && (
                    title.toLowerCase().includes('edit') ||
                    aria.toLowerCase().includes('edit')  ||
                    dga.toLowerCase().includes('edit')   ||
                    cls.includes('pencil') || cls.includes('naukicon')
                )){
                    res.push(el.tagName+'|'+cls+'|'+title+'|'+aria+'|'+dga);
                }
            }
            return res.slice(0,10);
        """)
        log.info(f"  Edit elements found: {edit_info}")

        # Force all edit elements visible
        driver.execute_script("""
            var els = document.querySelectorAll(
                '[class*="edit"],[class*="Edit"],[title*="Edit"],[title*="edit"]'
            );
            for(var i=0;i<els.length;i++){
                els[i].style.display    = 'block';
                els[i].style.visibility = 'visible';
                els[i].style.opacity    = '1';
                els[i].style.pointerEvents = 'auto';
            }
        """)
        time.sleep(0.5)

        # Try all possible edit button patterns
        EDIT_SELECTORS = [
            "//*[@title='Edit']",
            "//*[@title='edit']",
            "//*[contains(@aria-label,'edit') or contains(@aria-label,'Edit')]",
            "//*[contains(@data-ga-track,'edit') or contains(@data-ga-track,'Basic')]",
            "//*[contains(@class,'naukicon-edit')]",
            "//*[contains(@class,'icon-edit') or contains(@class,'pencil')]",
            "//*[contains(@class,'editContainer') or contains(@class,'profileEditIcon')]",
            "//button[.//svg]",
            "(//span[contains(@class,'edit')])[1]",
            "(//*[contains(@class,'edit')])[1]",
        ]

        name_clicked = False
        for sel in EDIT_SELECTORS:
            try:
                els = driver.find_elements(By.XPATH, sel)
                for el in els[:3]:
                    try:
                        if not el.is_displayed():
                            continue
                        driver.execute_script("arguments[0].scrollIntoView(true);", el)
                        time.sleep(0.3)
                        driver.execute_script("arguments[0].click();", el)
                        time.sleep(2)
                        # Check if name input appeared
                        inputs = driver.find_elements(By.XPATH,
                            "//input[contains(translate(@placeholder,"
                            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'name')"
                            " or @name='fullName' or @id='fullName' or @name='name']"
                        )
                        if inputs:
                            name_clicked = True
                            log.info(f"  ✅ Name editor opened via: {sel[:50]}")
                            break
                        dismiss_popups(driver)
                    except Exception:
                        continue
                if name_clicked:
                    break
            except Exception:
                continue

        if name_clicked:
            for inp_sel in [
                "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'name')]",
                "//input[@name='fullName']",
                "//input[@id='fullName']",
                "//input[@name='name']",
                "//input[@type='text'][1]",
            ]:
                try:
                    els = driver.find_elements(By.XPATH, inp_sel)
                    for el in els:
                        if el.is_displayed() and el.is_enabled():
                            el.click()
                            el.send_keys(Keys.CONTROL + "a")
                            el.clear()
                            el.send_keys(name_today)
                            time.sleep(0.5)
                            log.info(f"  Name entered: {name_today}")
                            # Save
                            for save_sel in [
                                "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]",
                                "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'update')]",
                                "//button[@type='submit']",
                            ]:
                                try:
                                    btn = WebDriverWait(driver, 4).until(
                                        EC.element_to_be_clickable((By.XPATH, save_sel))
                                    )
                                    driver.execute_script("arguments[0].click();", btn)
                                    time.sleep(2)
                                    log.info(f"  ✅ Name updated to: {name_today}")
                                    with open(flag_file, "w") as f:
                                        f.write(today_str)
                                    break
                                except TimeoutException:
                                    continue
                            break
                    break
                except Exception:
                    continue
        else:
            log.warning(f"  Could not find name edit button. Elements: {edit_info}")

    except Exception as e:
        log.warning(f"  Profile update failed (non-critical): {e}")


# ═══════════════════════════════════════════════════════════════
#  Main agent
# ═══════════════════════════════════════════════════════════════
def run_agent():
    log.info("\n" + "=" * 55)
    log.info(f"  Run started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 55)

    applied_log = load_json(CONFIG["applied_log"])
    log.info(f"Previously applied: {len(applied_log)} jobs")

    driver = create_driver()
    total  = 0

    try:
        if not login(driver):
            log.error("Login failed — stopping.")
            return

        loc = CONFIG["location"].lower()   # hyderabad

        # ── Daily profile name update ──────────────────────────────
        update_profile_name(driver)

        # ── SECTION 0: Newly arrived (last 24 hrs) ─────────────────
        log.info("\n" + "█" * 55)
        log.info("  SECTION 0 — Newly Arrived Jobs & Internships (24 hrs)")
        log.info("█" * 55)

        for kw in CONFIG["search_keywords"] + CONFIG["internship_keywords"]:
            slug = kw.lower().replace(" ", "-")
            for url, label, is_intern, save_redir in [
                (f"https://www.naukri.com/{slug}-jobs-in-{loc}?jobAge=1&experience=0",
                 "S0-HYD", False, True),
                (f"https://www.naukri.com/{slug}-jobs?jobAge=1&experience=0&wfhType=remote,hybrid",
                 "S0-WFH", False, False),
            ]:
                cards = get_cards(driver, url)
                log.info(f"  [{label}] {kw}: {len(cards)} listings")
                total += process_cards(driver, cards, applied_log,
                                       is_internship=is_intern,
                                       save_if_redirected=save_redir,
                                       section_label=label)

        # ── SECTION 1: Hyderabad jobs ──────────────────────────────
        log.info("\n" + "█" * 55)
        log.info("  SECTION 1 — Hyderabad Jobs (last 24 hrs)")
        log.info("█" * 55)

        for kw in CONFIG["search_keywords"]:
            slug = kw.lower().replace(" ", "-")
            url  = f"https://www.naukri.com/{slug}-jobs-in-{loc}?jobAge=1&experience=0"
            cards = get_cards(driver, url)
            log.info(f"  [S1] {kw}: {len(cards)} listings")
            total += process_cards(driver, cards, applied_log,
                                   save_if_redirected=True, section_label="S1")

        # ── SECTION 2: Hyderabad internships ───────────────────────
        log.info("\n" + "█" * 55)
        log.info(f"  SECTION 2 — Hyderabad Internships (stipend ≥ ₹{CONFIG['min_stipend']:,}/mo)")
        log.info("█" * 55)

        for kw in CONFIG["internship_keywords"]:
            slug     = kw.lower().replace(" ", "-")
            loc_slug = loc.replace(" ", "-")
            for url in [
                f"https://www.naukri.com/internship/{slug}-internship-in-{loc_slug}?jobAge=1",
                f"https://www.naukri.com/{slug}-internship-jobs-in-{loc_slug}?jobtype=Internship&jobAge=1",
            ]:
                cards = get_cards(driver, url)
                if cards:
                    log.info(f"  [S2] {kw}: {len(cards)} listings")
                    total += process_cards(driver, cards, applied_log,
                                           is_internship=True, save_if_redirected=True,
                                           section_label="S2")
                    break

        # ── SECTION 3: Remote / WFH jobs ───────────────────────────
        log.info("\n" + "█" * 55)
        log.info("  SECTION 3 — Remote / WFH Jobs (last 24 hrs)")
        log.info("█" * 55)

        for kw in CONFIG["search_keywords"]:
            slug = kw.lower().replace(" ", "-")
            url  = f"https://www.naukri.com/{slug}-jobs?jobAge=1&experience=0&wfhType=remote,hybrid"
            cards = get_cards(driver, url)
            log.info(f"  [S3] {kw}: {len(cards)} listings")
            total += process_cards(driver, cards, applied_log,
                                   save_if_redirected=False, section_label="S3")

        # ── SECTION 4: Remote / WFH internships ────────────────────
        log.info("\n" + "█" * 55)
        log.info("  SECTION 4 — Remote / WFH Internships (last 24 hrs)")
        log.info("█" * 55)

        for kw in CONFIG["internship_keywords"]:
            slug = kw.lower().replace(" ", "-")
            for url in [
                f"https://www.naukri.com/internship/{slug}-internship?wfhType=remote,hybrid&jobAge=1",
                f"https://www.naukri.com/{slug}-internship-jobs?jobtype=Internship&wfhType=remote,hybrid&jobAge=1",
            ]:
                cards = get_cards(driver, url)
                if cards:
                    log.info(f"  [S4] {kw}: {len(cards)} listings")
                    total += process_cards(driver, cards, applied_log,
                                           is_internship=True, save_if_redirected=False,
                                           section_label="S4")
                    break

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    log.info("\n" + "=" * 55)
    log.info(f"  Run complete — Applied this session : {total}")
    log.info(f"  Total ever applied                  : {len(load_json(CONFIG['applied_log']))}")
    log.info("=" * 55)


# ═══════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    is_ci = os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("CI") == "true"
    if is_ci:
        log.info("GitHub Actions — single run mode")
        run_agent()
    else:
        log.info("Local mode — running now then scheduling every 4 hrs")
        run_agent()
        schedule.every(4).hours.do(run_agent)
        while True:
            schedule.run_pending()
            time.sleep(30)
