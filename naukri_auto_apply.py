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
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    log_placeholder = None


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
        "full stack developer", "fullstack developer", "full stack engineer", "fullstack engineer",
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
        "dotnet developer", ".net developer", "react developer",
        "angular developer", "vue developer", "node developer",
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

    # ── Groq AI ──────────────────────────────────────────────────
    "groq_api_key":         os.getenv("GROQ_API_KEY", ""),
    "groq_model":           "llama3-70b-8192",
    "ai_match_threshold":   7,   # Score out of 10 — apply if >= this
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
#  Groq AI — Smart job matching + custom cover letter
# ═══════════════════════════════════════════════════════════════

CANDIDATE_PROFILE = """
Name         : Nagarjuna Pulabala
Degree       : B.Tech CSE (AI & ML) — BVRIT Hyderabad, 2026
Experience   : Fresher (0 years)
Location     : Hyderabad
Core Skills  : Python, Java, SQL, MySQL, PostgreSQL
AI/ML Skills : Machine Learning, Deep Learning, NLP, LangChain,
               RAG, HuggingFace, FAISS, Streamlit
Roles Seeking: Python Developer, Java Developer, Data Analyst,
               AI/ML Engineer, Software Engineer, SQL Developer
"""

_groq_client = None

def get_groq_client():
    global _groq_client
    if _groq_client is None and GROQ_AVAILABLE and CONFIG["groq_api_key"]:
        _groq_client = Groq(api_key=CONFIG["groq_api_key"])
    return _groq_client


def ai_job_match(job_title, job_description):
    """
    Uses Groq LLM to evaluate if the job is a good fit.
    Returns (score: int, reason: str)
    Score 1-10: >= threshold means apply, < threshold means skip.
    Falls back to True (apply) if Groq is unavailable.
    """
    client = get_groq_client()
    if not client:
        return 8, "Groq unavailable — defaulting to apply"

    prompt = f"""You are a job matching assistant. Evaluate if the job below is a good fit for this candidate.

CANDIDATE PROFILE:
{CANDIDATE_PROFILE}

JOB TITLE: {job_title}

JOB DESCRIPTION:
{job_description[:2000]}

Rate the match from 1-10 where:
10 = Perfect match
7-9 = Good match, apply
4-6 = Partial match, borderline
1-3 = Poor match, skip

Rules:
- Score >= 7 means the bot should apply
- Score < 7 means the bot should skip
- If job requires senior/lead/manager experience, score 1
- If job is non-IT (mechanical, sales, HR, etc.), score 1
- If job matches candidate skills well, score 7-10

Respond in EXACTLY this format (no other text):
SCORE: <number>
REASON: <one line reason>"""

    try:
        response = client.chat.completions.create(
            model=CONFIG["groq_model"],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.1,
        )
        text = response.choices[0].message.content.strip()
        lines = text.splitlines()
        score_line  = next((l for l in lines if l.startswith("SCORE:")),  "SCORE: 5")
        reason_line = next((l for l in lines if l.startswith("REASON:")), "REASON: No reason")
        score  = int(re.search(r"\d+", score_line).group())
        reason = reason_line.replace("REASON:", "").strip()
        return score, reason
    except Exception as e:
        log.warning(f"  [AI] Groq error: {e} — defaulting to apply")
        return 8, "Groq error — defaulting to apply"


def ai_cover_letter(job_title, job_description):
    """
    Uses Groq to generate a custom cover letter for the job.
    Returns cover letter string or None if unavailable.
    """
    client = get_groq_client()
    if not client:
        return None

    prompt = f"""Write a short, professional cover letter for this job application.

CANDIDATE PROFILE:
{CANDIDATE_PROFILE}

JOB TITLE: {job_title}

JOB DESCRIPTION:
{job_description[:1500]}

Instructions:
- Keep it under 100 words
- Mention 2-3 relevant skills from candidate profile that match the job
- Sound enthusiastic but professional
- Do NOT include subject line or date
- Start directly with "I am..."
- End with "Thank you for your consideration."

Write ONLY the cover letter, nothing else."""

    try:
        response = client.chat.completions.create(
            model=CONFIG["groq_model"],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.4,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log.warning(f"  [AI] Cover letter error: {e}")
        return None

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

        # ── Groq AI match check ───────────────────────────────────
        ai_score, ai_reason = ai_job_match(job_title, page_text)
        log.info(f"  [AI] Score: {ai_score}/10 — {ai_reason}")
        if ai_score < CONFIG["ai_match_threshold"]:
            log.info(f"  [AI] Skipping (score {ai_score} < {CONFIG['ai_match_threshold']}): {job_title}")
            driver.close()
            driver.switch_to.window(original)
            return False
        log.info(f"  [AI] ✅ Good match (score {ai_score}) — proceeding to apply")

        # ── Generate AI cover letter ──────────────────────────────
        ai_cl = ai_cover_letter(job_title, page_text)
        if ai_cl:
            CONFIG["cover_letter"] = ai_cl
            log.info(f"  [AI] Cover letter generated ({len(ai_cl)} chars)")

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
    log.info("  DAILY PROFILE UPDATE — Alternating Resume Headline")
    log.info("─" * 55)

    is_odd = date.today().toordinal() % 2 == 1
    headline_odd  = "Python Developer | Java | SQL | AI ML Engineer | Data Analyst | Fresher | B.Tech CSE AI&ML"
    headline_even = "AI ML Engineer | Python Developer | Data Analyst | Java | SQL | Fresher | B.Tech CSE AIML"
    headline_today = headline_odd if is_odd else headline_even
    log.info(f"  Today's headline ({'odd' if is_odd else 'even'} day): {headline_today}")

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

        # ── CONFIRMED: Naukri uses class 'new-pencil' for edit buttons ──
        # Found from debug log: 'SPAN|new-pencil|||'

        # First scroll to headline section
        try:
            headline_section = driver.find_element(By.XPATH,
                "//*[contains(@class,'resumeHeadline')] | "
                "//*[contains(@class,'headline')] | "
                "//*[contains(text(),'Resume Headline')]/ancestor::div[1]"
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", headline_section)
            time.sleep(1)
        except Exception:
            pass

        EDIT_SELECTORS = [
            # CONFIRMED class from debug log
            "//span[contains(@class,'new-pencil')]",
            "//*[contains(@class,'new-pencil')]",
            # Headline section specific
            "//*[contains(@class,'resumeHeadline')]//span[contains(@class,'new-pencil')]",
            "//*[contains(@class,'resumeHeadline')]//*[contains(@class,'new-pencil')]",
            # Try second pencil (first might be for name/photo)
            "(//span[contains(@class,'new-pencil')])[2]",
            "(//span[contains(@class,'new-pencil')])[1]",
            # Fallbacks
            "//*[@title='Edit']",
            "//*[contains(@aria-label,'headline') or contains(@aria-label,'Headline')]",
        ]

        name_clicked = False
        for sel in EDIT_SELECTORS:
            try:
                els = driver.find_elements(By.XPATH, sel)
                log.info(f"  [headline] Trying: {sel[:60]} — found {len(els)} elements")
                for el in els[:5]:
                    try:
                        if not el.is_displayed():
                            driver.execute_script(
                                "arguments[0].style.display='block';"
                                "arguments[0].style.visibility='visible';", el
                            )
                        driver.execute_script("arguments[0].scrollIntoView(true);", el)
                        time.sleep(0.3)
                        driver.execute_script("arguments[0].click();", el)
                        time.sleep(2)
                        # Check if headline input appeared
                        inputs = driver.find_elements(By.XPATH,
                            "//input[contains(translate(@placeholder,"
                            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'headline')"
                            " or @name='resumeHeadline' or @id='resumeHeadline']"
                            " | //textarea[contains(translate(@placeholder,"
                            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'headline')]"
                            " | //input[@type='text'] | //textarea"
                        )
                        if inputs:
                            name_clicked = True
                            log.info(f"  ✅ Headline editor opened via: {sel[:60]}")
                            break
                        dismiss_popups(driver)
                    except Exception:
                        continue
                if name_clicked:
                    break
            except Exception:
                continue

        if name_clicked:
            time.sleep(3)
            headline_filled = False

            # Method 1: Use active element (focused input after modal opens)
            try:
                active_el = driver.switch_to.active_element
                tag = active_el.tag_name.lower()
                if tag in ("input", "textarea") and active_el.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView(true);", active_el)
                    active_el.click()
                    active_el.send_keys(Keys.CONTROL + "a")
                    active_el.send_keys(Keys.DELETE)
                    active_el.clear()
                    time.sleep(0.3)
                    active_el.send_keys(headline_today)
                    time.sleep(0.5)
                    log.info(f"  [Method 1] Headline entered via active element: {headline_today[:40]}")
                    headline_filled = True
            except Exception as e:
                log.info(f"  [Method 1] Active element failed: {e}")

            # Method 2: JS — set value directly on all visible inputs/textareas
            if not headline_filled:
                try:
                    result = driver.execute_script("""
                        var inputs = document.querySelectorAll('input[type="text"], textarea');
                        var filled = [];
                        for(var i=0; i<inputs.length; i++){
                            var el = inputs[i];
                            var rect = el.getBoundingClientRect();
                            if(rect.width > 0 && rect.height > 0){
                                var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                                    window.HTMLInputElement.prototype, 'value') ||
                                    Object.getOwnPropertyDescriptor(
                                    window.HTMLTextAreaElement.prototype, 'value');
                                if(nativeInputValueSetter && nativeInputValueSetter.set){
                                    nativeInputValueSetter.set.call(el, arguments[0]);
                                } else {
                                    el.value = arguments[0];
                                }
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                                filled.push(el.tagName + '|' + (el.placeholder||'') + '|' + (el.name||''));
                            }
                        }
                        return filled;
                    """, headline_today)
                    if result:
                        log.info(f"  [Method 2] JS filled {len(result)} inputs: {result[:3]}")
                        headline_filled = True
                    else:
                        log.warning("  [Method 2] No visible inputs found")
                except Exception as e:
                    log.warning(f"  [Method 2] JS method failed: {e}")

            # Method 3: Try all visible inputs/textareas with send_keys
            if not headline_filled:
                try:
                    all_inputs = driver.find_elements(By.XPATH, "//input[@type='text'] | //textarea")
                    log.info(f"  [Method 3] Found {len(all_inputs)} text inputs/textareas")
                    for el in all_inputs:
                        try:
                            if el.is_displayed() and el.is_enabled():
                                driver.execute_script("arguments[0].scrollIntoView(true);", el)
                                el.click()
                                time.sleep(0.3)
                                el.send_keys(Keys.CONTROL + "a")
                                el.send_keys(Keys.DELETE)
                                el.clear()
                                time.sleep(0.3)
                                el.send_keys(headline_today)
                                time.sleep(0.3)
                                log.info(f"  [Method 3] Typed into: {el.tag_name} placeholder={el.get_attribute('placeholder')}")
                                headline_filled = True
                                break
                        except Exception:
                            continue
                except Exception as e:
                    log.warning(f"  [Method 3] Failed: {e}")

            # Save
            if headline_filled:
                saved = False
                for save_sel in [
                    "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]",
                    "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'update')]",
                    "//button[@type='submit']",
                    "//input[@type='submit']",
                ]:
                    try:
                        btn = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, save_sel))
                        )
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(3)
                        log.info(f"  ✅ Headline updated to: {headline_today}")
                        with open(flag_file, "w") as f:
                            f.write(today_str)
                        saved = True
                        break
                    except TimeoutException:
                        continue
                if not saved:
                    log.warning("  Could not find Save button after filling headline")
            else:
                log.warning("  All 3 methods failed to fill headline input")
        else:
            log.warning(f"  Could not find headline edit button. Elements: {edit_info}")

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
            url  = f"https://www.naukri.com/{slug}-jobs-in-{loc}?jobAge=2&experience=0"
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
                f"https://www.naukri.com/internship/{slug}-internship-in-{loc_slug}?jobAge=2",
                f"https://www.naukri.com/{slug}-internship-jobs-in-{loc_slug}?jobtype=Internship&jobAge=2",
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
            url  = f"https://www.naukri.com/{slug}-jobs?jobAge=2&experience=0&wfhType=remote,hybrid"
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
                f"https://www.naukri.com/internship/{slug}-internship?wfhType=remote,hybrid&jobAge=2",
                f"https://www.naukri.com/{slug}-internship-jobs?jobtype=Internship&wfhType=remote,hybrid&jobAge=2",
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