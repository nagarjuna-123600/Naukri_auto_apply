"""
Naukri Auto-Apply Bot  -  CLEAN BUILD
=======================================
Sections:
  0 - Newly arrived jobs & internships (last 24 hrs, Hyderabad + WFH)
  1 - Hyderabad jobs
  2 - Hyderabad internships (stipend >= 10,000/month)
  3 - Remote / WFH jobs
  4 - Remote / WFH internships

Features:
  Cookie-based login (fallback to email+password)
  Skill + location filter on actual job page
  Saves redirected Hyderabad jobs to Naukri saved jobs
  Duplicate prevention via applied_jobs.json
  Daily name alternation to refresh profile timestamp
  GitHub Actions compatible (headless Chrome)
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
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
import re, time, logging, json, os, schedule
from datetime import datetime, date


# ==============================================================
#  CONFIG
# ==============================================================
CONFIG = {
    # Login
    "email":    os.getenv("NAUKRI_EMAIL",    "pulabalanagarjuna07@gmail.com"),
    "password": os.getenv("NAUKRI_PASSWORD", "your_password"),

    # Job search
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

    # Internship keywords
    "internship_keywords": [
        "Java Intern",
        "Python Intern",
        "SQL Intern",
        "AIML Intern",
        "Data Analyst Intern",
        "Software Developer Intern",
    ],

    "location":    "Hyderabad",
    "min_stipend": 10000,

    # Required skills (any one match = apply)
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

    # Exclude keywords (skip if found in job title)
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
        "data entry", "back office",
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

    # Form answers
    "current_ctc":        "3",
    "expected_ctc":       "3",
    "notice_period_days": 15,
    "cover_letter":       None,

    # Limits
    "max_apply_per_search": 10,
    "action_delay":          2,

    # Files
    "applied_log":  "applied_jobs.json",
    "manual_log":   "manual_apply_jobs.json",
    "headless":     False,
}


# ==============================================================
#  Logging
# ==============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s ***%(levelname)s*** %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("naukri_bot.log"),
    ],
)
log = logging.getLogger(__name__)


# ==============================================================
#  Applied-jobs tracker
# ==============================================================
def load_json(path):
    if os.path.exists(path):
        try:
            content = open(path).read().strip()
            return json.loads(content) if content else {}
        except Exception:
            return {}
    return {}


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ==============================================================
#  Browser
# ==============================================================
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
        log.info("[driver] Headless mode")
    else:
        options.add_argument("--start-maximized")
        log.info("[driver] Visible mode")

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
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins',   {get: () => [1,2,3,4,5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
        window.chrome = {runtime: {}};
    """})
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(5)
    return driver


# ==============================================================
#  Popup dismisser
# ==============================================================
def dismiss_popups(driver):
    XPATHS = [
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'skip')]",
        "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'skip')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'maybe later')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'not now')]",
        "//*[contains(@class,'close-btn') or contains(@class,'closeBtn') or contains(@class,'crossIcon')]",
        "//*[contains(@class,'modal-close') or contains(@class,'overlayClose')]",
        "//button[@aria-label='Close' or @aria-label='close' or @aria-label='Dismiss']",
        "//*[@data-testid='modal-close'] | //*[@data-testid='close-button']",
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
    except Exception:
        pass
    return dismissed


# ==============================================================
#  Login  (cookie first, fallback to email+password)
# ==============================================================
def login(driver):
    # Try cookie login
    cookie_str = os.getenv("NAUKRI_COOKIES", "")
    if cookie_str:
        try:
            log.info("Trying cookie login...")
            driver.get("https://www.naukri.com")
            time.sleep(3)
            cookies = json.loads(cookie_str)
            log.info(f"Loading {len(cookies)} cookies...")
            for c in cookies:
                try:
                    c.pop("sameSite", None)
                    driver.add_cookie(c)
                except Exception:
                    pass
            driver.refresh()
            time.sleep(4)
            if _is_logged_in(driver):
                log.info("Cookie login successful!")
                dismiss_popups(driver)
                return True
            log.warning("Cookie login failed - trying email/password")
        except Exception as e:
            log.warning(f"Cookie error: {e}")

    # Fallback: email + password login
    log.info("Email/password login...")
    driver.get("https://www.naukri.com/nlogin/login")
    time.sleep(5)
    wait = WebDriverWait(driver, 20)
    try:
        ef = wait.until(EC.element_to_be_clickable((By.ID, "usernameField")))
        ef.clear()
        for c in CONFIG["email"]:
            ef.send_keys(c)
            time.sleep(0.04)
        time.sleep(0.5)

        pf = driver.find_element(By.ID, "passwordField")
        pf.clear()
        for c in CONFIG["password"]:
            pf.send_keys(c)
            time.sleep(0.04)
        time.sleep(0.5)

        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        time.sleep(4)
        dismiss_popups(driver)

        if _is_logged_in(driver):
            log.info("Email/password login successful!")
            return True
        log.error("Login failed - check credentials!")
        return False
    except Exception as e:
        log.error(f"Login error: {e}")
        return False


def _is_logged_in(driver):
    try:
        driver.find_element(By.XPATH,
            "//*[contains(@class,'nI-gNb-drawer__icon') or "
            "contains(@class,'user-icon') or contains(@class,'avatar')]"
        )
        return True
    except NoSuchElementException:
        pass
    return "naukri.com" in driver.current_url and "nlogin" not in driver.current_url


# ==============================================================
#  Skill & location filters
# ==============================================================
def is_matching_job(title, description=""):
    t = title.lower()
    d = description.lower()
    for ex in CONFIG["exclude_keywords"]:
        if ex.lower() in t:
            log.info(f"  Skipping (excluded '{ex}'): {title}")
            return False
    for skill in CONFIG["required_skills"]:
        if skill in t or skill in d:
            return True
    log.info(f"  Skipping (no skill match): {title}")
    return False


def is_valid_location(driver):
    ALLOWED = ["hyderabad", "work from home", "remote", "hybrid", "wfh", "telangana"]
    try:
        for sel in [
            "//*[contains(@class,'location')]",
            "//*[contains(@class,'loc')]",
            "//*[@data-qa='job-location']",
        ]:
            for el in driver.find_elements(By.XPATH, sel):
                txt = el.text.strip().lower()
                if not txt:
                    continue
                if any(a in txt for a in ALLOWED):
                    log.info(f"  Location OK: {el.text.strip()}")
                    return True
                if len(txt) > 2:
                    log.info(f"  Wrong location: {el.text.strip()} - skipping")
                    return False
    except Exception:
        pass
    return True


def has_required_skill_on_page(driver, job_title):
    try:
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
    except Exception:
        body = job_title.lower()

    # Non-IT signals
    non_it = [
        "mechanical engineer", "electrical engineer", "civil engineer",
        "chemical engineer", "production engineer", "automobile engineer",
        "embedded systems", "vlsi", "hardware engineer",
    ]
    if any(s in body for s in non_it):
        log.info(f"  Skipping (non-IT signal): {job_title}")
        return False

    for skill in CONFIG["required_skills"]:
        if skill in body:
            return True

    log.info(f"  Skipping (no skill on page): {job_title}")
    return False


# ==============================================================
#  Save manual job (redirected Hyderabad jobs)
# ==============================================================
def save_manual_job(job_url, job_title, reason):
    manual_log = load_json(CONFIG["manual_log"])
    if job_url not in manual_log:
        manual_log[job_url] = {
            "title":    job_title,
            "reason":   reason,
            "saved_at": datetime.now().isoformat(),
        }
        save_json(CONFIG["manual_log"], manual_log)
        log.info(f"  Saved to manual log ({reason}): {job_title}")


def save_job_on_naukri(driver, job_url, job_title):
    """Click the Naukri Save button for redirected Hyderabad jobs."""
    original = driver.current_window_handle
    try:
        driver.execute_script(f"window.open('{job_url}', '_blank');")
        driver.switch_to.window(driver.window_handles[-1])
        time.sleep(3)
        dismiss_popups(driver)

        SAVE_SELECTORS = [
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]",
            "//*[contains(@class,'save-job')]",
            "//*[contains(@class,'saveJob')]",
            "//*[@title='Save Job']",
            "//span[contains(text(),'Save')]",
        ]
        for sel in SAVE_SELECTORS:
            try:
                btn = WebDriverWait(driver, 4).until(EC.element_to_be_clickable((By.XPATH, sel)))
                driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", btn)
                log.info(f"  Saved on Naukri: {job_title}")
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


# ==============================================================
#  Application form handler
# ==============================================================
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


def _best_notice(select_el, days):
    sel = Select(select_el)
    parsed = []
    for opt in sel.options:
        txt = opt.text.strip().lower()
        if not txt or txt in ("select", "choose", "--"):
            continue
        n = 0 if "immediate" in txt else None
        if n is None:
            m = re.search(r"\d+", txt)
            if m:
                n = int(m.group())
        if n is not None:
            parsed.append((n, opt.text.strip()))
    if not parsed:
        return None
    best = None
    for n, txt in sorted(parsed):
        if n <= days:
            best = txt
    return best or sorted(parsed)[0][1]


def handle_form(driver):
    CTC_CUR  = ["current ctc", "current salary", "present ctc", "ctc (current)"]
    CTC_EXP  = ["expected ctc", "expected salary", "desired ctc", "ctc (expected)"]
    NOTICE   = ["notice period", "joining period", "available to join"]
    COVER    = ["cover letter", "cover note", "message to recruiter"]
    SKIP_CV  = "No cover letter available at this time."
    found = False

    for _ in range(6):
        dismiss_popups(driver)
        time.sleep(0.8)

        if not driver.find_elements(By.XPATH,
            "//form | //div[contains(@class,'modal')] | //div[contains(@class,'apply')]"):
            break

        for el in driver.find_elements(By.XPATH,
            "//input[not(@type='hidden') and not(@type='submit') "
            "and not(@type='checkbox') and not(@type='radio') and not(@type='file')] "
            "| //textarea | //select"):
            try:
                if not el.is_displayed() or not el.is_enabled():
                    continue
                tag  = el.tag_name.lower()
                lbl  = ""
                fid  = el.get_attribute("id") or ""
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
                    _fill_text(driver, el, CONFIG["current_ctc"])
                    found = True
                elif any(k in lbl for k in CTC_EXP) and tag == "input":
                    _fill_text(driver, el, CONFIG["expected_ctc"])
                    found = True
                elif any(k in lbl for k in NOTICE) and tag == "select":
                    best = _best_notice(el, CONFIG["notice_period_days"])
                    if best:
                        Select(el).select_by_visible_text(best)
                        found = True
                elif any(k in lbl for k in NOTICE) and tag == "input":
                    _fill_text(driver, el, str(CONFIG["notice_period_days"]))
                    found = True
                elif any(k in lbl for k in COVER) and tag == "textarea":
                    _fill_text(driver, el, CONFIG["cover_letter"] or SKIP_CV)
                    found = True
            except StaleElementReferenceException:
                continue
            except Exception:
                continue

        # Click Next / Submit
        clicked = False
        for txt in ["submit", "apply now", "apply", "next", "continue"]:
            try:
                btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH,
                    f"//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
                    f"'abcdefghijklmnopqrstuvwxyz'),'{txt}')]"
                )))
                driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                time.sleep(0.4)
                driver.execute_script("arguments[0].click();", btn)
                clicked = True
                found   = True
                time.sleep(1.5)
                dismiss_popups(driver)
                break
            except Exception:
                continue
        if not clicked:
            break
    return found


# ==============================================================
#  Apply to a single job
# ==============================================================
def apply_to_job(driver, job_url, job_title, applied_log, is_hyderabad=True):
    if job_url in applied_log:
        log.info(f"  Already applied: {job_title}")
        return False

    original = driver.current_window_handle
    driver.execute_script(f"window.open('{job_url}', '_blank');")
    driver.switch_to.window(driver.window_handles[-1])
    time.sleep(CONFIG["action_delay"])

    try:
        dismiss_popups(driver)

        # Location check
        if not is_valid_location(driver):
            log.info(f"  Wrong location: {job_title}")
            driver.close()
            driver.switch_to.window(original)
            return False

        # Skill check on full page
        if not has_required_skill_on_page(driver, job_title):
            driver.close()
            driver.switch_to.window(original)
            return False

        # Find Apply button
        wait = WebDriverWait(driver, 10)
        apply_btn = None
        for sel in [
            "//button[contains(text(),'Apply')]",
            "//a[contains(text(),'Apply')]",
            "//button[@id='apply-button']",
            "//*[contains(@class,'apply-button')]",
            "//button[contains(@class,'applyBtn')]",
            "//*[@data-ga-track='Apply']",
        ]:
            try:
                apply_btn = wait.until(EC.element_to_be_clickable((By.XPATH, sel)))
                break
            except TimeoutException:
                continue

        if not apply_btn:
            log.info(f"  No Apply button: {job_title}")
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
        time.sleep(1.5)

        # Check for external redirect
        page   = driver.page_source.lower()
        cururl = driver.current_url.lower()
        EXT_KEYWORDS = [
            "apply on company website", "apply via company",
            "apply via email", "apply via whatsapp",
            "send your resume", "email your cv",
        ]
        is_external = any(k in page for k in EXT_KEYWORDS)
        if not is_external and "naukri.com" not in cururl:
            is_external = True

        if is_external:
            if is_hyderabad:
                log.info(f"  External redirect - saving on Naukri: {job_title}")
                save_manual_job(job_url, job_title, "external_redirect")
                driver.close()
                driver.switch_to.window(original)
                save_job_on_naukri(driver, job_url, job_title)
            else:
                log.info(f"  External redirect - skipping WFH job: {job_title}")
                driver.close()
                driver.switch_to.window(original)
            return False

        dismiss_popups(driver)
        handle_form(driver)

        log.info(f"  Applied: {job_title}")
        applied_log[job_url] = {
            "title":      job_title,
            "applied_at": datetime.now().isoformat(),
            "url":        job_url,
        }
        driver.close()
        driver.switch_to.window(original)
        return True

    except ElementClickInterceptedException:
        log.info(f"  Click blocked: {job_title}")
        try:
            driver.close()
            driver.switch_to.window(original)
        except Exception:
            pass
        return False
    except Exception as e:
        log.warning(f"  Error on {job_title}: {str(e)[:60]}")
        try:
            driver.close()
            driver.switch_to.window(original)
        except Exception:
            pass
        return False


# ==============================================================
#  Job cards extractor
# ==============================================================
def get_cards(driver, url):
    driver.get(url)
    time.sleep(CONFIG["action_delay"])
    dismiss_popups(driver)
    for _ in range(3):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
    cards = driver.find_elements(By.CLASS_NAME, "cust-job-tuple")
    if not cards:
        for css in [".srp-jobtuple-wrapper", "[data-job-id]"]:
            cards = driver.find_elements(By.CSS_SELECTOR, css)
            if cards:
                break
    return cards


def extract_card(driver, card):
    try:
        try:
            el = card.find_element(By.CLASS_NAME, "title")
        except NoSuchElementException:
            el = card.find_element(By.TAG_NAME, "a")
        title = el.text.strip()
        url   = el.get_attribute("href") or card.find_element(By.TAG_NAME, "a").get_attribute("href")
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


def extract_stipend(text):
    if not text:
        return 0
    t = text.lower().replace(",", "").replace("rs", "").replace("inr", "").strip()
    if "unpaid" in t:
        return 0
    m = re.search(r"(\d+(?:\.\d+)?)\s*k", t)
    if m:
        return int(float(m.group(1)) * 1000)
    nums = re.findall(r"\d+", t)
    if nums:
        val = int(nums[0])
        if "lpa" in t:
            return int(val * 100000 / 12)
        return val
    return 0


def process_cards(driver, cards, applied_log, is_internship=False, is_hyderabad=True):
    count = 0
    for card in cards:
        if count >= CONFIG["max_apply_per_search"]:
            break
        try:
            info = extract_card(driver, card)
            if not info:
                continue
            title, url, desc = info

            log.info(f"  Checking: {title}")

            # Skill check on card
            if not is_matching_job(title, desc):
                continue

            # Stipend check for internships
            if is_internship:
                stipend_text = ""
                for cls in ["salary", "stipend", "package"]:
                    try:
                        stipend_text = card.find_element(By.CLASS_NAME, cls).text
                        break
                    except NoSuchElementException:
                        continue
                if extract_stipend(stipend_text) < CONFIG["min_stipend"]:
                    log.info(f"  Low stipend: {title}")
                    continue

            success = apply_to_job(driver, url, title, applied_log, is_hyderabad=is_hyderabad)
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


# ==============================================================
#  Daily profile name update
# ==============================================================
def update_profile_name(driver):
    FLAG_FILE = "profile_updated_date.txt"
    today_str = str(date.today())

    # Run only once per day
    if os.path.exists(FLAG_FILE):
        try:
            if open(FLAG_FILE).read().strip() == today_str:
                log.info("Profile already updated today - skipping")
                return
        except Exception:
            pass

    log.info("\n" + "-" * 55)
    log.info("  DAILY PROFILE UPDATE - Refreshing name")
    log.info("-" * 55)

    is_odd = date.today().toordinal() % 2 == 1
    name_today = "Pulabala Nagarjuna" if is_odd else "Nagarjuna Pulabala"
    log.info(f"  Today's name ({'odd' if is_odd else 'even'} day): {name_today}")

    try:
        driver.get("https://www.naukri.com/mnjuser/profile?id=&altresid")
        time.sleep(8)
        dismiss_popups(driver)
        time.sleep(2)

        # Log all edit-related elements for debugging
        all_btns = driver.execute_script("""
            var results = [];
            var tags = ['button','span','i','a','div'];
            for (var t = 0; t < tags.length; t++) {
                var els = document.getElementsByTagName(tags[t]);
                for (var i = 0; i < els.length; i++) {
                    var el = els[i];
                    var cls   = el.getAttribute('class') || '';
                    var title = el.getAttribute('title') || '';
                    var aria  = el.getAttribute('aria-label') || '';
                    var dataga = el.getAttribute('data-ga-track') || '';
                    var rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0 && (
                        title.toLowerCase().includes('edit') ||
                        aria.toLowerCase().includes('edit') ||
                        dataga.toLowerCase().includes('edit') ||
                        cls.toLowerCase().includes('pencil') ||
                        cls.toLowerCase().includes('naukicon') ||
                        cls.toLowerCase().includes('icon-edit'))) {
                        results.push(tags[t] + '|' + cls + '|' + title + '|' + aria + '|' + dataga);
                    }
                }
            }
            return results.slice(0, 10);
        """)
        log.info(f"  Edit elements on page: {all_btns}")

        # Force-reveal all edit elements
        driver.execute_script("""
            var els = document.querySelectorAll(
                '[class*="edit"],[class*="Edit"],[title*="edit"],[title*="Edit"]'
            );
            for (var i = 0; i < els.length; i++) {
                els[i].style.display    = 'block';
                els[i].style.visibility = 'visible';
                els[i].style.opacity    = '1';
                els[i].style.pointerEvents = 'auto';
            }
        """)
        time.sleep(1)

        NAME_EDIT_SELECTORS = [
            "//*[@title='Edit']",
            "//*[@title='edit']",
            "//*[contains(@title,'Edit')]",
            "//*[contains(@aria-label,'edit') or contains(@aria-label,'Edit')]",
            "//*[contains(@data-ga-track,'edit') or contains(@data-ga-track,'Edit')]",
            "//*[contains(@data-ga-track,'Basic') or contains(@data-ga-track,'basic')]",
            "//*[contains(@class,'naukicon-edit')]",
            "//*[contains(@class,'icon-edit')]",
            "//*[contains(@class,'pencil')]",
            "//button[.//svg]",
            "//*[contains(@class,'editContainer')]",
            "//*[contains(@class,'profileEditIcon')]",
            "(//*[contains(@class,'edit')])[1]",
            "(//span[contains(@class,'edit')])[1]",
        ]

        name_clicked = False
        for sel in NAME_EDIT_SELECTORS:
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
                        inputs = driver.find_elements(By.XPATH,
                            "//input[contains(translate(@placeholder,"
                            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'name')"
                            " or @name='fullName' or @id='fullName']"
                        )
                        if inputs:
                            name_clicked = True
                            log.info(f"  Opened name editor via: {sel[:50]}")
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
                log.info(f"  Entered name: {name_today}")

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
                        log.info(f"  Name updated to: {name_today}")
                        with open(FLAG_FILE, "w") as f:
                            f.write(today_str)
                        break
                    except TimeoutException:
                        continue
            else:
                log.warning("  Could not find name input field")
        else:
            log.warning(f"  Name edit button not found. Elements: {all_btns}")

    except Exception as e:
        log.warning(f"  Profile update failed: {e}")


# ==============================================================
#  Main agent
# ==============================================================
def run_agent():
    log.info("\n" + "=" * 60)
    log.info(f"  Run started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

    applied_log = load_json(CONFIG["applied_log"])
    log.info(f"Previously applied: {len(applied_log)} jobs")

    driver = create_driver()
    total  = 0

    try:
        if not login(driver):
            log.error("Login failed - stopping.")
            return

        loc = CONFIG["location"].lower()   # hyderabad

        # ── Daily profile name update ──────────────────────────
        update_profile_name(driver)

        # ── SECTION 0: Newly arrived (last 24 hrs) ────────────
        log.info("\n" + "█" * 60)
        log.info("  SECTION 0 - Newly Arrived Jobs & Internships (Last 24 hrs)")
        log.info("█" * 60)

        for kw in CONFIG["search_keywords"] + CONFIG["internship_keywords"]:
            slug = kw.lower().replace(" ", "-")
            for url in [
                f"https://www.naukri.com/{slug}-jobs-in-{loc}?jobAge=1&experience=0",
                f"https://www.naukri.com/{slug}-jobs?jobAge=1&experience=0&wfhType=remote,hybrid",
            ]:
                is_hyd = "wfhType" not in url
                cards  = get_cards(driver, url)
                log.info(f"  [{kw}] Found {len(cards)} new listings")
                n = process_cards(driver, cards, applied_log, is_hyderabad=is_hyd)
                total += n

        # ── SECTION 1: Hyderabad jobs ─────────────────────────
        log.info("\n" + "█" * 60)
        log.info("  SECTION 1 - Hyderabad Jobs")
        log.info("█" * 60)

        for kw in CONFIG["search_keywords"]:
            slug = kw.lower().replace(" ", "-")
            url  = f"https://www.naukri.com/{slug}-jobs-in-{loc}?jobAge=1&experience=0"
            cards = get_cards(driver, url)
            log.info(f"  [{kw}] Found {len(cards)} listings")
            n = process_cards(driver, cards, applied_log, is_hyderabad=True)
            total += n

        # ── SECTION 2: Hyderabad internships ─────────────────
        log.info("\n" + "█" * 60)
        log.info(f"  SECTION 2 - Hyderabad Internships (stipend >= Rs.{CONFIG['min_stipend']:,}/mo)")
        log.info("█" * 60)

        for kw in CONFIG["internship_keywords"]:
            slug    = kw.lower().replace(" ", "-")
            loc_slug = loc.replace(" ", "-")
            for url in [
                f"https://www.naukri.com/internship/{slug}-internship-in-{loc_slug}?jobAge=1",
                f"https://www.naukri.com/{slug}-internship-jobs-in-{loc_slug}?jobtype=Internship&jobAge=1",
            ]:
                cards = get_cards(driver, url)
                if cards:
                    log.info(f"  [{kw}] Found {len(cards)} internship listings")
                    n = process_cards(driver, cards, applied_log, is_internship=True, is_hyderabad=True)
                    total += n
                    break

        # ── SECTION 3: Remote/WFH jobs ────────────────────────
        log.info("\n" + "█" * 60)
        log.info("  SECTION 3 - Remote / WFH Jobs")
        log.info("█" * 60)

        for kw in CONFIG["search_keywords"]:
            slug  = kw.lower().replace(" ", "-")
            url   = f"https://www.naukri.com/{slug}-jobs?jobAge=1&experience=0&wfhType=remote,hybrid"
            cards = get_cards(driver, url)
            log.info(f"  [{kw}] Found {len(cards)} WFH listings")
            n = process_cards(driver, cards, applied_log, is_hyderabad=False)
            total += n

        # ── SECTION 4: Remote/WFH internships ────────────────
        log.info("\n" + "█" * 60)
        log.info("  SECTION 4 - Remote / WFH Internships")
        log.info("█" * 60)

        for kw in CONFIG["internship_keywords"]:
            slug = kw.lower().replace(" ", "-")
            for url in [
                f"https://www.naukri.com/internship/{slug}-internship?wfhType=remote,hybrid&jobAge=1",
                f"https://www.naukri.com/{slug}-internship-jobs?jobtype=Internship&wfhType=remote,hybrid&jobAge=1",
            ]:
                cards = get_cards(driver, url)
                if cards:
                    log.info(f"  [{kw}] Found {len(cards)} WFH internship listings")
                    n = process_cards(driver, cards, applied_log, is_internship=True, is_hyderabad=False)
                    total += n
                    break

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    log.info("\n" + "=" * 60)
    log.info(f"  Run complete - Applied this session: {total}")
    log.info(f"  Total ever applied: {len(load_json(CONFIG['applied_log']))}")
    log.info("=" * 60)


# ==============================================================
#  Entry point
# ==============================================================
if __name__ == "__main__":
    is_ci = os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("CI") == "true"
    if is_ci:
        log.info("GitHub Actions - single run mode")
        run_agent()
    else:
        log.info("Local mode - running now then scheduling every 4 hrs")
        run_agent()
        schedule.every(4).hours.do(run_agent)
        while True:
            schedule.run_pending()
            time.sleep(60)
