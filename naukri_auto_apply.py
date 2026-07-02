"""
Naukri Auto-Apply Bot  ─  PLAYWRIGHT VERSION
=============================================
Features:
  ✅ Auto login (cookie-based + email/password fallback)
  ✅ SECTION 1 — Regular Jobs        (Java / Python / SQL Developer, Hyderabad)
  ✅ SECTION 2 — Internships         (Java / Python / SQL, stipend ≥ ₹10,000/month)
  ✅ SECTION 3 — Remote / WFH Jobs   (Java, Python, SQL, Software Engineer/Developer)
  ✅ SECTION 4 — WFH Internships
  ✅ Dismisses ALL popups
  ✅ Fills multi-step application forms (CTC, Notice Period, Cover Letter)
  ✅ Saves non-Hyderabad jobs to Naukri Saved Jobs
  ✅ Saves failed-apply jobs to Naukri Saved Jobs
  ✅ Duplicate prevention (applied_jobs.json)
  ✅ Headless mode for GitHub Actions
  ✅ Full logging to console + naukri_bot.log

Requirements:
    pip install playwright schedule
    playwright install chromium
"""

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
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
    "experience_min": 0,
    "experience_max": None,

    # ── Internship search ────────────────────────────────────────
    "internship_keywords": [
        "Java Intern",
        "Python Intern",
        "SQL Intern",
        "AIML Intern",
        "Data Analyst",
    ],
    "min_stipend": 10000,

    # ── Skill filter ────────────────────────────────────────────
    "required_skills": [
        "java", "python", "sql", "mysql", "postgresql",
        "software engineer", "associate software engineer",
        "customer software engineer", "software developer",
        "langchain", "rag", "huggingface", "faiss", "streamlit",
        "junior developer", "trainee", "intern", "fresher",
        "java developer", "python developer", "sql developer",
        "ai", "ml", "machine learning", "deep learning",
        "data analyst", "data science",
    ],

    # ── Title keywords that cause a job to be SKIPPED ───────────
    "exclude_keywords": [
        "senior", "lead", "manager", "architect",
        "web developer", "frontend developer", "front-end developer",
        "backend developer", "back-end developer",
        "full stack developer", "fullstack developer",
    ],

    # ── Application form answers ────────────────────────────────
    "current_ctc":        "3",
    "expected_ctc":       "3",
    "notice_period_days": 15,
    "cover_letter":       None,

    # ── Run limits ───────────────────────────────────────────────
    "max_apply_per_search": 10,
    "action_delay":          2,

    # ── Scheduler ────────────────────────────────────────────────
    "schedule_times": ["09:00", "18:00"],

    # ── Misc ─────────────────────────────────────────────────────
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
            log.warning("  [load] applied_jobs.json was corrupt/empty — starting fresh")
            return {}
    return {}

def save_applied(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ═══════════════════════════════════════════════════════════════
#  Browser setup — Playwright
# ═══════════════════════════════════════════════════════════════
def create_browser(playwright):
    is_ci = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"
    headless = is_ci or CONFIG["headless"]

    if headless:
        log.info("  [driver] Running in headless mode (CI/server detected)")
    else:
        log.info("  [driver] Running in visible mode (local laptop)")

    browser = playwright.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled",
            "--disable-notifications",
            "--disable-infobars",
            "--lang=en-US",
        ]
    )

    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="Asia/Kolkata",
    )

    # Stealth — override webdriver detection
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
        window.chrome = {runtime: {}};
    """)

    page = context.new_page()
    page.set_default_timeout(30000)
    page.set_default_navigation_timeout(30000)
    return browser, context, page


# ═══════════════════════════════════════════════════════════════
#  Popup / modal dismisser
# ═══════════════════════════════════════════════════════════════
def dismiss_popups(page):
    CLOSE_XPATHS = [
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
        "//*[@data-testid='close-button']",
        "//div[contains(@class,'loginModal')]//button[contains(@class,'close')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'got it')]",
        "//button[normalize-space(text())='×' or normalize-space(text())='✕' or normalize-space(text())='✖']",
    ]

    dismissed = 0
    for _pass in range(4):
        found = False
        for xpath in CLOSE_XPATHS:
            try:
                els = page.locator(f"xpath={xpath}").all()
                for el in els:
                    try:
                        if el.is_visible():
                            el.click(force=True, timeout=2000)
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
        page.keyboard.press("Escape")
        time.sleep(0.3)
    except Exception:
        pass

    if dismissed:
        log.info(f"  [popup] Total dismissed: {dismissed}")
    return dismissed


# ═══════════════════════════════════════════════════════════════
#  Multi-step application form handler
# ═══════════════════════════════════════════════════════════════
def _fill_text_field(page, locator, value):
    try:
        locator.scroll_into_view_if_needed()
        locator.click()
        locator.fill("")
        locator.type(str(value), delay=30)
        time.sleep(0.3)
        return True
    except Exception:
        return False


def _best_notice_option(options, preferred_days):
    parsed = []
    for opt in options:
        txt = opt.lower().strip()
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
            parsed.append((num, opt))

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


def handle_application_form(page):
    CTC_CURRENT_KEYWORDS  = ["current ctc", "current salary", "current package", "present ctc"]
    CTC_EXPECTED_KEYWORDS = ["expected ctc", "expected salary", "expected package", "desired ctc"]
    NOTICE_KEYWORDS       = ["notice period", "notice", "joining period", "available to join"]
    COVER_LETTER_KEYWORDS = ["cover letter", "cover note", "message to recruiter", "about yourself"]
    SKIP_COVER_TEXT       = "No cover letter available at this time."

    form_found = False

    for step in range(6):
        dismiss_popups(page)
        time.sleep(0.8)

        # Check if a form/modal is present
        containers = page.locator("form, div[class*='modal'], div[class*='apply'], div[class*='chatbot']").all()
        if not containers:
            break

        # Process all visible inputs
        inputs = page.locator(
            "input:not([type='hidden']):not([type='submit']):not([type='checkbox'])"
            ":not([type='radio']):not([type='file']), textarea, select"
        ).all()

        for el in inputs:
            try:
                if not el.is_visible():
                    continue

                tag = el.evaluate("e => e.tagName.toLowerCase()")
                etype = (el.get_attribute("type") or "").lower()

                # Build label text
                label_text = ""
                fid = el.get_attribute("id") or ""
                if fid:
                    try:
                        lbl = page.locator(f"label[for='{fid}']").first
                        label_text = lbl.inner_text().strip().lower()
                    except Exception:
                        pass
                if not label_text:
                    label_text = (el.get_attribute("placeholder") or "").lower()
                if not label_text:
                    label_text = (el.get_attribute("aria-label") or "").lower()
                if not label_text:
                    try:
                        parent_text = el.evaluate(
                            "e => e.closest('div,li,tr')?.innerText || ''"
                        )
                        label_text = (parent_text or "").lower()[:100]
                    except Exception:
                        pass

                # Current CTC
                if any(k in label_text for k in CTC_CURRENT_KEYWORDS):
                    if tag == "input" and etype in ("text", "number", ""):
                        if _fill_text_field(page, el, CONFIG["current_ctc"]):
                            log.info(f"  [form] Filled Current CTC → {CONFIG['current_ctc']} LPA")
                            form_found = True

                # Expected CTC
                elif any(k in label_text for k in CTC_EXPECTED_KEYWORDS):
                    if tag == "input" and etype in ("text", "number", ""):
                        if _fill_text_field(page, el, CONFIG["expected_ctc"]):
                            log.info(f"  [form] Filled Expected CTC → {CONFIG['expected_ctc']} LPA")
                            form_found = True

                # Notice Period — dropdown
                elif any(k in label_text for k in NOTICE_KEYWORDS) and tag == "select":
                    options = el.locator("option").all_inner_texts()
                    best = _best_notice_option(options, CONFIG["notice_period_days"])
                    if best:
                        try:
                            el.select_option(label=best)
                            log.info(f"  [form] Selected Notice Period → '{best}'")
                            form_found = True
                        except Exception as ex:
                            log.warning(f"  [form] Notice dropdown failed: {ex}")

                # Notice Period — text input
                elif any(k in label_text for k in NOTICE_KEYWORDS) and tag == "input":
                    if _fill_text_field(page, el, str(CONFIG["notice_period_days"])):
                        log.info(f"  [form] Filled Notice Period → {CONFIG['notice_period_days']} days")
                        form_found = True

                # Cover Letter
                elif any(k in label_text for k in COVER_LETTER_KEYWORDS) and tag == "textarea":
                    cover = CONFIG.get("cover_letter") or SKIP_COVER_TEXT
                    if _fill_text_field(page, el, cover):
                        log.info("  [form] Filled Cover Letter")
                        form_found = True

            except Exception as ex:
                log.debug(f"  [form] Field error: {ex}")
                continue

        # Handle radio buttons for notice period
        radios = page.locator("input[type='radio']").all()
        for radio in radios:
            try:
                if not radio.is_visible():
                    continue
                rlabel = ""
                rid = radio.get_attribute("id") or ""
                if rid:
                    try:
                        lbl = page.locator(f"label[for='{rid}']").first
                        rlabel = lbl.inner_text().strip().lower()
                    except Exception:
                        pass
                if not rlabel:
                    rlabel = (radio.get_attribute("value") or "").lower()

                is_immediate = "immediate" in rlabel or rlabel in ("0", "0 days")
                is_15 = "15" in rlabel

                if is_immediate or is_15:
                    if not radio.is_checked():
                        radio.click(force=True)
                        log.info(f"  [form] Selected notice radio → '{rlabel}'")
                        form_found = True
                        break
            except Exception:
                continue

        # Click Next / Continue / Submit
        next_clicked = False
        for btn_xpath in [
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'apply now')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'apply')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
        ]:
            try:
                btn = page.locator(f"xpath={btn_xpath}").first
                if btn.is_visible():
                    btn.scroll_into_view_if_needed()
                    time.sleep(0.4)
                    btn.click()
                    log.info(f"  [form] Clicked → '{btn.inner_text().strip()}'")
                    next_clicked = True
                    form_found = True
                    time.sleep(1.5)
                    dismiss_popups(page)
                    break
            except Exception:
                continue

        if not next_clicked:
            break

    return form_found


# ═══════════════════════════════════════════════════════════════
#  Cookie-based login
# ═══════════════════════════════════════════════════════════════
def login_with_cookies(context, page):
    cookies_json = os.environ.get("NAUKRI_COOKIES", "")
    if not cookies_json:
        log.info("No NAUKRI_COOKIES found — skipping cookie login")
        return False

    try:
        cookies = json.loads(cookies_json)
        log.info(f"Loading {len(cookies)} cookies...")

        page.goto("https://www.naukri.com", wait_until="domcontentloaded")
        time.sleep(3)

        # Convert cookies to Playwright format
        pw_cookies = []
        for cookie in cookies:
            c = {
                "name":   cookie["name"],
                "value":  cookie["value"],
                "domain": cookie.get("domain", ".naukri.com"),
                "path":   cookie.get("path", "/"),
                "secure": cookie.get("secure", False),
                "httpOnly": cookie.get("httpOnly", False),
            }
            if "expirationDate" in cookie and not cookie.get("session", False):
                c["expires"] = int(cookie["expirationDate"])
            if cookie.get("sameSite"):
                same = cookie["sameSite"].lower()
                if same == "no_restriction":
                    c["sameSite"] = "None"
                elif same == "lax":
                    c["sameSite"] = "Lax"
                elif same == "strict":
                    c["sameSite"] = "Strict"
            pw_cookies.append(c)

        context.add_cookies(pw_cookies)

        page.goto("https://www.naukri.com/mnjuser/homepage", wait_until="domcontentloaded")
        time.sleep(4)
        dismiss_popups(page)

        if "homepage" in page.url or "mnjuser" in page.url:
            log.info("✅ Cookie login successful!")
            return True
        else:
            log.warning("Cookie login failed — will try email/password")
            return False

    except Exception as e:
        log.error(f"Cookie login error: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
#  Login
# ═══════════════════════════════════════════════════════════════
def login(context, page, email, password):
    if login_with_cookies(context, page):
        return True

    log.info("Trying email/password login...")
    page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")
    time.sleep(5)

    try:
        email_field = page.locator("#usernameField")
        email_field.wait_for(state="visible", timeout=20000)
        email_field.click()
        time.sleep(0.5)
        email_field.fill("")
        for char in email:
            email_field.type(char, delay=50)
        time.sleep(1)

        pwd_field = page.locator("#passwordField")
        pwd_field.wait_for(state="visible", timeout=10000)
        pwd_field.click()
        time.sleep(0.5)
        pwd_field.fill("")
        for char in password:
            pwd_field.type(char, delay=50)
        time.sleep(1)

        page.locator("button[type='submit']").click()
        page.wait_for_url("**/naukri.com/**", timeout=20000)
        time.sleep(CONFIG["action_delay"])
        log.info("Login successful!")
        dismiss_popups(page)
        return True

    except PlaywrightTimeoutError:
        log.error("Login failed — check credentials or Naukri UI may have changed.")
        return False


# ═══════════════════════════════════════════════════════════════
#  Search jobs
# ═══════════════════════════════════════════════════════════════
def search_jobs(page, keyword, location):
    log.info(f"Searching: '{keyword}' in '{location}'...")
    url = (
        f"https://www.naukri.com/{keyword.lower().replace(' ', '-')}-jobs-in-"
        f"{location.lower()}?jobAge=3&experience=0"
    )
    page.goto(url, wait_until="domcontentloaded")
    time.sleep(CONFIG["action_delay"])
    dismiss_popups(page)

    for _ in range(3):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)

    cards = page.locator(".cust-job-tuple").all()
    if not cards:
        for sel in [".srp-jobtuple-wrapper", "[data-job-id]", ".job-tuple-comp"]:
            cards = page.locator(sel).all()
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
# ═══════════════════════════════════════════════════════════════
def search_internships(page, keyword, location):
    log.info(f"  Searching internships: '{keyword}' in '{location}'...")
    slug = keyword.lower().replace(" ", "-")
    loc  = location.lower().replace(" ", "-")
    url  = f"https://www.naukri.com/internship/{slug}-internship-in-{loc}?jobAge=7"
    url_alt = f"https://www.naukri.com/{slug}-internship-jobs-in-{loc}?jobtype=Internship&jobAge=7"

    page.goto(url, wait_until="domcontentloaded")
    time.sleep(CONFIG["action_delay"])
    dismiss_popups(page)

    cards = page.locator(".cust-job-tuple").all()
    if not cards:
        page.goto(url_alt, wait_until="domcontentloaded")
        time.sleep(CONFIG["action_delay"])
        dismiss_popups(page)

    for _ in range(3):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)

    cards = page.locator(".cust-job-tuple").all()
    if not cards:
        for sel in [".srp-jobtuple-wrapper", "[data-job-id]", ".job-tuple-comp"]:
            cards = page.locator(sel).all()
            if cards:
                break

    log.info(f"  Found {len(cards)} internship listings")
    return cards


# ═══════════════════════════════════════════════════════════════
#  Stipend extractor
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
        if "lpa" in t or "per annum" in t or "annual" in t:
            return int(val * 100000 / 12)
        return val
    return 0


# ═══════════════════════════════════════════════════════════════
#  Internship match filter
# ═══════════════════════════════════════════════════════════════
def is_matching_internship(title, description, stipend_text):
    title_lower = title.lower()
    desc_lower  = description.lower()

    skill_match = any(
        s in title_lower or s in desc_lower
        for s in CONFIG["required_skills"]
    )
    if not skill_match:
        log.info(f"  Skipping internship (no skill match): {title}")
        return False

    for ex in CONFIG["exclude_keywords"]:
        if ex.lower() in title_lower:
            log.info(f"  Skipping internship (excluded keyword '{ex}'): {title}")
            return False

    stipend = extract_stipend(stipend_text)
    if stipend < CONFIG["min_stipend"]:
        log.info(f"  Skipping internship (stipend ₹{stipend:,} < ₹{CONFIG['min_stipend']:,}): {title}")
        return False

    log.info(f"  ✔ Internship matches — stipend ₹{stipend:,}/month: {title}")
    return True


# ═══════════════════════════════════════════════════════════════
#  Location extractor
# ═══════════════════════════════════════════════════════════════
def get_job_location(card):
    LOCATION_SELECTORS = [
        "span.locWdth", "span.location", ".loc",
        ".jobTuple-location", "li.location"
    ]
    for sel in LOCATION_SELECTORS:
        try:
            loc = card.locator(sel).first.inner_text(timeout=2000).strip()
            if loc:
                return loc.lower()
        except Exception:
            continue
    return ""


# ═══════════════════════════════════════════════════════════════
#  Save manual apply log
# ═══════════════════════════════════════════════════════════════
def save_manual_job(job_url, job_title, reason):
    manual_log_path = "manual_apply_jobs.json"
    if os.path.exists(manual_log_path):
        with open(manual_log_path) as f:
            try:
                manual_log = json.load(f)
            except Exception:
                manual_log = {}
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


# ═══════════════════════════════════════════════════════════════
#  Save job on Naukri (non-Hyderabad / failed apply)
# ═══════════════════════════════════════════════════════════════
def save_job_on_naukri(context, page, job_url, job_title):
    new_page = context.new_page()
    try:
        new_page.goto(job_url, wait_until="domcontentloaded")
        time.sleep(4)
        dismiss_popups(new_page)
        time.sleep(2)

        SAVE_SELECTORS = [
            "//button[contains(text(),'Save')]",
            "//a[contains(text(),'Save')]",
            "//*[contains(@class,'save-job')]",
            "//*[contains(@class,'saveJob')]",
            "//*[@title='Save Job']",
            "//span[contains(text(),'Save')]",
            "//*[contains(@data-ga-track,'Save')]",
        ]
        saved = False
        for sel in SAVE_SELECTORS:
            try:
                btn = new_page.locator(f"xpath={sel}").first
                if btn.is_visible(timeout=5000):
                    btn.scroll_into_view_if_needed()
                    time.sleep(0.5)
                    btn.click(force=True)
                    time.sleep(1)
                    log.info(f"  💾 Saved on Naukri: {job_title}")
                    saved = True
                    break
            except Exception:
                continue

        if not saved:
            log.warning(f"  ⚠️ Could not find Save button: {job_title}")
    except Exception as e:
        log.warning(f"  Could not save on Naukri: {e}")
    finally:
        new_page.close()


# ═══════════════════════════════════════════════════════════════
#  Apply to a single job
# ═══════════════════════════════════════════════════════════════
def apply_to_job(context, page, job_url, job_title, applied_log):
    if job_url in applied_log:
        log.info(f"  Already applied: {job_title}")
        return False

    new_page = context.new_page()
    try:
        new_page.goto(job_url, wait_until="domcontentloaded")
        time.sleep(CONFIG["action_delay"])

        dismiss_popups(new_page)

        # Save job on Naukri first
        SAVE_SELECTORS = [
            "//button[contains(text(),'Save')]",
            "//a[contains(text(),'Save')]",
            "//*[contains(@class,'save-job')]",
            "//*[contains(@class,'saveJob')]",
            "//*[@title='Save Job']",
            "//*[@data-ga-track='Save']",
        ]
        for sel in SAVE_SELECTORS:
            try:
                save_btn = new_page.locator(f"xpath={sel}").first
                if save_btn.is_visible(timeout=3000):
                    save_btn.click(force=True)
                    time.sleep(0.5)
                    log.info(f"  💾 Saved on Naukri: {job_title}")
                    break
            except Exception:
                continue

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
                btn = new_page.locator(f"xpath={selector}").first
                if btn.is_visible(timeout=5000):
                    apply_btn = btn
                    break
            except Exception:
                continue

        if not apply_btn:
            log.warning(f"  No Apply button found — saving: {job_title}")
            save_manual_job(job_url, job_title, "no_apply_button")
            # Try saving on Naukri
            for sel in SAVE_SELECTORS:
                try:
                    btn = new_page.locator(f"xpath={sel}").first
                    if btn.is_visible(timeout=3000):
                        btn.click(force=True)
                        log.info(f"  💾 Saved on Naukri (no apply button): {job_title}")
                        break
                except Exception:
                    continue
            new_page.close()
            return False

        apply_btn.scroll_into_view_if_needed()
        time.sleep(1)
        dismiss_popups(new_page)
        time.sleep(0.5)

        try:
            apply_btn.click()
        except Exception:
            apply_btn.click(force=True)
        log.info(f"  Clicked Apply: {job_title}")
        time.sleep(1.5)

        # Check for external apply
        page_text = new_page.content().lower()
        current_url = new_page.url.lower()

        external_reasons = {
            "company website": ["apply on company website", "apply via company", "external application"],
            "email": ["apply via email", "send your resume", "email your cv"],
            "whatsapp": ["apply via whatsapp", "whatsapp to apply"],
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
            new_page.close()
            return False

        dismiss_popups(new_page)
        form_handled = handle_application_form(new_page)
        if form_handled:
            log.info(f"  [form] Form completed: {job_title}")

        # Final confirmation
        for confirm_xpath in [
            "//button[contains(text(),'Apply')]",
            "//button[contains(text(),'Submit')]",
            "//button[contains(text(),'Confirm')]",
        ]:
            try:
                confirm = new_page.locator(f"xpath={confirm_xpath}").first
                if confirm.is_visible(timeout=3000):
                    confirm.click()
                    time.sleep(1)
                    break
            except Exception:
                continue

        log.info(f"  ✅ Applied: {job_title}")
        applied_log[job_url] = {
            "title":      job_title,
            "applied_at": datetime.now().isoformat(),
            "url":        job_url,
        }
        new_page.close()
        return True

    except Exception as e:
        log.error(f"  Error applying to {job_title}: {e}")
        # Try saving on Naukri even if apply failed
        try:
            for sel in [
                "//button[contains(text(),'Save')]",
                "//*[contains(@class,'save-job')]",
                "//*[@title='Save Job']",
            ]:
                try:
                    btn = new_page.locator(f"xpath={sel}").first
                    if btn.is_visible(timeout=2000):
                        btn.click(force=True)
                        log.info(f"  💾 Saved on Naukri (error fallback): {job_title}")
                        break
                except Exception:
                    continue
            save_manual_job(job_url, job_title, f"error: {str(e)[:50]}")
        except Exception:
            pass
        try:
            new_page.close()
        except Exception:
            pass
        return False


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

    with sync_playwright() as playwright:
        browser, context, page = create_browser(playwright)

        try:
            if not login(context, page, CONFIG["email"], CONFIG["password"]):
                return

            total_applied = 0

            # ── SECTION 1: Regular Jobs ───────────────────────────
            log.info("\n" + "█" * 55)
            log.info("  SECTION 1 OF 4 — Regular Jobs")
            log.info("█" * 55)

            for keyword in CONFIG["search_keywords"]:
                log.info(f"\n{'─'*50}")
                log.info(f"Keyword: {keyword}")
                log.info(f"{'─'*50}")

                job_cards = search_jobs(page, keyword, CONFIG["location"])
                applied_this_round = 0

                for card in job_cards:
                    if applied_this_round >= CONFIG["max_apply_per_search"]:
                        log.info(f"Reached max ({CONFIG['max_apply_per_search']}) for '{keyword}'")
                        break
                    try:
                        try:
                            title_el = card.locator(".title").first
                            job_title = title_el.inner_text(timeout=2000).strip()
                            job_url = title_el.get_attribute("href")
                        except Exception:
                            title_el = card.locator("a").first
                            job_title = title_el.inner_text(timeout=2000).strip()
                            job_url = title_el.get_attribute("href")

                        if not job_title or not job_url:
                            continue

                        try:
                            desc = card.locator(".job-description").first.inner_text(timeout=2000)
                        except Exception:
                            try:
                                desc = card.locator(".job-desc").first.inner_text(timeout=2000)
                            except Exception:
                                desc = ""

                        log.info(f"Checking: {job_title}")

                        if is_matching_job(job_title, desc):
                            job_loc = get_job_location(card)
                            if job_loc and "hyderabad" not in job_loc:
                                log.info(f"  📍 Non-Hyderabad ({job_loc}) — saving: {job_title}")
                                save_job_on_naukri(context, page, job_url, job_title)
                            else:
                                success = apply_to_job(context, page, job_url, job_title, applied_log)
                                if success:
                                    applied_this_round += 1
                                    total_applied += 1
                                    save_applied(CONFIG["log_file"], applied_log)
                                    time.sleep(CONFIG["action_delay"])

                    except Exception as e:
                        log.warning(f"  Skipping card: {e}")
                        continue

            # ── SECTION 2: Internships ────────────────────────────
            log.info("\n" + "█" * 55)
            log.info("  SECTION 2 OF 4 — Internships")
            log.info(f"  Stipend filter: ≥ ₹{CONFIG['min_stipend']:,} / month")
            log.info("█" * 55)

            for keyword in CONFIG["internship_keywords"]:
                log.info(f"\n{'─'*50}")
                log.info(f"Internship keyword: {keyword}")
                log.info(f"{'─'*50}")

                intern_cards = search_internships(page, keyword, CONFIG["location"])
                applied_this_round = 0

                for card in intern_cards:
                    if applied_this_round >= CONFIG["max_apply_per_search"]:
                        break
                    try:
                        try:
                            title_el = card.locator(".title").first
                            job_title = title_el.inner_text(timeout=2000).strip()
                            job_url = title_el.get_attribute("href")
                        except Exception:
                            title_el = card.locator("a").first
                            job_title = title_el.inner_text(timeout=2000).strip()
                            job_url = title_el.get_attribute("href")

                        if not job_title or not job_url:
                            continue

                        try:
                            desc = card.locator(".job-description").first.inner_text(timeout=2000)
                        except Exception:
                            try:
                                desc = card.locator(".job-desc").first.inner_text(timeout=2000)
                            except Exception:
                                desc = ""

                        stipend_text = ""
                        for stipend_cls in ["salary", "stipend", "package", "compensation", "ctc"]:
                            try:
                                stipend_text = card.locator(f".{stipend_cls}").first.inner_text(timeout=1000)
                                if stipend_text:
                                    break
                            except Exception:
                                continue

                        if not stipend_text:
                            try:
                                full_text = card.inner_text(timeout=2000)
                                m = re.search(r"(?:stipend|₹|inr|salary)[\s:]*[\d,k]+", full_text, re.IGNORECASE)
                                if m:
                                    stipend_text = m.group()
                            except Exception:
                                pass

                        log.info(f"Checking internship: {job_title} | stipend: '{stipend_text}'")

                        if is_matching_internship(job_title, desc, stipend_text):
                            intern_loc = get_job_location(card)
                            if intern_loc and "hyderabad" not in intern_loc:
                                log.info(f"  📍 Non-Hyderabad internship ({intern_loc}) — saving: {job_title}")
                                save_job_on_naukri(context, page, job_url, job_title)
                            else:
                                success = apply_to_job(context, page, job_url, job_title, applied_log)
                                if success:
                                    applied_this_round += 1
                                    total_applied += 1
                                    save_applied(CONFIG["log_file"], applied_log)
                                    time.sleep(CONFIG["action_delay"])

                    except Exception as e:
                        log.warning(f"  Skipping internship card: {e}")
                        continue

            # ── SECTION 3: WFH Jobs ───────────────────────────────
            log.info("\n" + "█" * 55)
            log.info("  SECTION 3 OF 4 — Work From Home Jobs")
            log.info("█" * 55)

            wfh_keywords = [kw + " work from home" for kw in CONFIG["search_keywords"]]

            for keyword in wfh_keywords:
                log.info(f"\n{'─'*50}")
                log.info(f"WFH Keyword: {keyword}")
                log.info(f"{'─'*50}")

                wfh_url = (
                    f"https://www.naukri.com/{keyword.lower().replace(' ', '-')}-jobs?"
                    f"jobAge=3&experience=0&wfhType=remote,hybrid"
                )
                page.goto(wfh_url, wait_until="domcontentloaded")
                time.sleep(CONFIG["action_delay"])
                dismiss_popups(page)

                for _ in range(3):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1)

                wfh_cards = page.locator(".cust-job-tuple").all()
                log.info(f"Found {len(wfh_cards)} WFH listings")
                applied_this_round = 0

                for card in wfh_cards:
                    if applied_this_round >= CONFIG["max_apply_per_search"]:
                        break
                    try:
                        try:
                            title_el = card.locator(".title").first
                            job_title = title_el.inner_text(timeout=2000).strip()
                            job_url = title_el.get_attribute("href")
                        except Exception:
                            title_el = card.locator("a").first
                            job_title = title_el.inner_text(timeout=2000).strip()
                            job_url = title_el.get_attribute("href")

                        if not job_title or not job_url:
                            continue

                        try:
                            desc = card.locator(".job-description").first.inner_text(timeout=2000)
                        except Exception:
                            try:
                                desc = card.locator(".job-desc").first.inner_text(timeout=2000)
                            except Exception:
                                desc = ""

                        log.info(f"Checking WFH: {job_title}")

                        if is_matching_job(job_title, desc):
                            success = apply_to_job(context, page, job_url, job_title, applied_log)
                            if success:
                                applied_this_round += 1
                                total_applied += 1
                                save_applied(CONFIG["log_file"], applied_log)
                                time.sleep(CONFIG["action_delay"])

                    except Exception as e:
                        log.warning(f"  Skipping WFH card: {e}")
                        continue

            # ── SECTION 4: WFH Internships ────────────────────────
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
                    page.goto(url, wait_until="domcontentloaded")
                    time.sleep(CONFIG["action_delay"])
                    dismiss_popups(page)
                    for _ in range(3):
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        time.sleep(1)
                    cards = page.locator(".cust-job-tuple").all()
                    if cards:
                        break

                log.info(f"  Found {len(cards)} WFH internship listings")
                applied_this_round = 0

                for card in cards:
                    if applied_this_round >= CONFIG["max_apply_per_search"]:
                        break
                    try:
                        try:
                            title_el = card.locator(".title").first
                            job_title = title_el.inner_text(timeout=2000).strip()
                            job_url = title_el.get_attribute("href")
                        except Exception:
                            title_el = card.locator("a").first
                            job_title = title_el.inner_text(timeout=2000).strip()
                            job_url = title_el.get_attribute("href")

                        if not job_title or not job_url:
                            continue

                        try:
                            desc = card.locator(".job-description").first.inner_text(timeout=2000)
                        except Exception:
                            try:
                                desc = card.locator(".job-desc").first.inner_text(timeout=2000)
                            except Exception:
                                desc = ""

                        stipend_text = ""
                        try:
                            stipend_text = card.locator("xpath=.//*[contains(@class,'stipend') or contains(@class,'salary')]").first.inner_text(timeout=1000)
                        except Exception:
                            pass

                        log.info(f"Checking WFH internship: {job_title}")

                        if is_matching_internship(job_title, desc, stipend_text):
                            success = apply_to_job(context, page, job_url, job_title, applied_log)
                            if success:
                                applied_this_round += 1
                                total_applied += 1
                                save_applied(CONFIG["log_file"], applied_log)
                                time.sleep(CONFIG["action_delay"])

                    except Exception as e:
                        log.warning(f"  Skipping WFH internship card: {e}")
                        continue

        finally:
            try:
                browser.close()
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
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    is_ci = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"

    if is_ci:
        log.info("GitHub Actions detected — running single pass and exiting.")
        run_agent()
        log.info("Single run complete. GitHub Actions will trigger next run on schedule.")
    else:
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
