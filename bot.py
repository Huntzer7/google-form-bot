"""
================================================================================
  Google Forms Automation Bot  (v3 — Smart Answer Modes)
  Using: undetected-chromedriver + Selenium
  Author: Expert Web Automation Developer

  Supported question types:
    ✅ หลายตัวเลือก    (Multiple Choice — role="radiogroup")
    ✅ ช่องทำเครื่องหมาย (Checkbox      — role="group" + role="checkbox")
    ✅ สเกลเชิงเส้น    (Linear Scale   — role="radiogroup")
    ✅ คะแนน           (Star Rating    — role="radiogroup")

  Answer modes (ใช้ได้กับทุกประเภทคำถาม):
    • "fixed"    → ล็อคตายตัว         เช่น เลือก index 2 เสมอ
    • "range"    → สุ่มในช่วง          เช่น สุ่มระหว่าง index 3–4 (ดาว 4–5)
    • "weighted" → สุ่มตามเปอร์เซนต์   เช่น 70% index 0, 30% index 1
    • (ไม่ระบุ)   → สุ่มเต็ม 100%      ทุก index มีสิทธิ์เท่ากัน
================================================================================

INSTALLATION:
    pip install undetected-chromedriver selenium

USAGE:
    1. Edit SECTION 1 (CONFIGURATION) below — ที่เดียวเท่านั้น
    2. Run: python google_forms_bot.py
================================================================================
"""
import json
import os
import time
import random
import traceback

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
)
import undetected_chromedriver as uc


# ============================================================
# SECTION 1: CONFIGURATION
# (แก้เฉพาะส่วนนี้เท่านั้น)
# ============================================================

# --- 1.1 Target URL ---
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSe8_ByL6g4ECx_XvzLd79qXJeJvaF8UWJYfYuZdR9EzL96BBw/viewform?usp=dialog"
# --- 1.2 Submission Mode ---
# True  → Mode A: Login ด้วย Google account ก่อนส่งแต่ละครั้ง
# False → Mode B: ส่งแบบ anonymous วนตาม LOOP_COUNT
LOGIN_REQUIRED = False

# --- 1.3 Mode A: บัญชี Google ---
# ACCOUNTS = [
#     {"email": "account1@gmail.com", "password": "password1"},
# ]

# ✅ อ่านจากไฟล์แทน
def load_accounts(filepath="gmail_list.txt") -> list:
    accounts = []
    try:
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if not line or ":" not in line:
                    continue
                email, password = line.split(":", 1)
                accounts.append({
                    "email": email.strip(),
                    "password": password.strip()
                })
        print(f"  [ACCOUNTS] โหลดสำเร็จ: {len(accounts)} บัญชี")
    except FileNotFoundError:
        print(f"  [ACCOUNTS] ❌ ไม่พบไฟล์ {filepath}")
    return accounts

ACCOUNTS = load_accounts()

# --- 1.4 Mode B: จำนวนครั้งที่ส่ง (ใช้เมื่อ LOGIN_REQUIRED = False) ---
LOOP_COUNT = 5

# ─────────────────────────────────────────────────────────────────────────────
# --- 1.5 ANSWER RULES — หัวใจของ script ---
#
# ANSWER_RULES คือ dict ที่ map "question_index (0-based)" → "กฎการตอบ"
# คำถามที่ไม่ได้ระบุ → สุ่มเต็ม 100% โดยอัตโนมัติ
#
# ┌──────────────────────────────────────────────────────────────────────────┐
# │ MODE          │ รูปแบบ                          │ คำอธิบาย              │
# ├──────────────────────────────────────────────────────────────────────────┤
# │ fixed         │ {"mode": "fixed", "value": N}   │ เลือก index N ตายตัว  │
# │               │                                 │ (0 = ตัวเลือกแรก)     │
# ├──────────────────────────────────────────────────────────────────────────┤
# │ range         │ {"mode": "range",               │ สุ่มในช่วง index       │
# │               │  "min": A, "max": B}            │ A ถึง B (รวมทั้งคู่)   │
# ├──────────────────────────────────────────────────────────────────────────┤
# │ weighted      │ {"mode": "weighted",            │ สุ่มตาม % ที่กำหนด    │
# │               │  "weights": {idx: pct, ...}}    │ ผลรวม % ไม่ต้อง = 100 │
# │               │                                 │ (normalize อัตโนมัติ)  │
# ├──────────────────────────────────────────────────────────────────────────┤
# │ checkbox_     │ {"mode": "checkbox_fixed",      │ checkbox: ติ๊กตายตัว  │
# │ fixed         │  "values": [0, 2]}              │ values = list ของ index│
# ├──────────────────────────────────────────────────────────────────────────┤
# │ checkbox_     │ {"mode": "checkbox_weighted",   │ checkbox: แต่ละช่องมี  │
# │ weighted      │  "weights": {0: 80, 1: 40,      │ % อิสระ ว่าจะถูกติ๊ก  │
# │               │              2: 60}}            │ (คิดแยกกันแต่ละช่อง)  │
# └──────────────────────────────────────────────────────────────────────────┘
#
# ตัวอย่างจริง:
# ANSWER_RULES = {
#     0: {"mode": "fixed",    "value": 1},              # ข้อ 1 → เลือกตัวเลือกที่ 2 เสมอ
#     1: {"mode": "range",    "min": 3, "max": 4},      # ข้อ 2 (ดาว5ดวง) → สุ่มแค่ 4★ หรือ 5★
#     2: {"mode": "weighted", "weights": {0:10, 1:20,   # ข้อ 3 → สุ่มตาม % ที่กำหนด
#                                         2:40, 3:20, 4:10}}
#     3: {"mode": "checkbox_fixed",    "values": [0,2]},# ข้อ 4 (checkbox) → ติ๊กช่อง 1,3
#     4: {"mode": "checkbox_weighted", "weights": {0:80, # ข้อ 5 (checkbox) → ช่อง 1 โอกาส 80%
#                                                  1:50, #                     ช่อง 2 โอกาส 50%
#                                                  2:20}},#                    ช่อง 3 โอกาส 20%
# }
# ─────────────────────────────────────────────────────────────────────────────
ANSWER_RULES = {
    # ตัวอย่าง — ลบออกและใส่กฎของตัวเองแทน:
    # 0: {"mode": "range",    "min": 3, "max": 4},   # สุ่มดาว 4-5 สำหรับคะแนน 5 ดาว
    # 1: {"mode": "weighted", "weights": {0:70, 1:30}},
    #2: {"mode": "fixed",    "value": 0},
}

# --- 1.6 DEFAULT_RULE — กฎสำรองสำหรับทุกข้อที่ไม่ได้ระบุใน ANSWER_RULES ---
#
# ใช้เมื่ออยากให้ "ทุกข้อ" ทำงานเหมือนกัน โดยไม่ต้องนับ index ทีละข้อ
# ข้อที่ระบุใน ANSWER_RULES จะ "ชนะ" DEFAULT_RULE เสมอ
#
# ตัวอย่างที่พบบ่อย:
#
#   ฟอร์มคะแนน (5 ดาว) ทุกข้อ → สุ่มแค่ 4★ หรือ 5★:
#   DEFAULT_RULE = {"mode": "range", "min": 3, "max": 4}
#
#   ฟอร์มสเกล 1–10 ทุกข้อ → สุ่มแค่ 8–10:
#   DEFAULT_RULE = {"mode": "range", "min": 7, "max": 9}
#
#   ฟอร์มหลายตัวเลือก ทุกข้อ → เลือกตัวเลือกที่ 1 เสมอ:
#   DEFAULT_RULE = {"mode": "fixed", "value": 0}
#
#   ฟอร์มติ๊ก Checkbox ระหว่างช่องในทุกข้อ
#   index 1 = ตัวเลือกที่ 2, index 2 = ตัวเลือกที่ 3, index 3 = ตัวเลือกที่ 4 (นับจาก 0)
#   weights: {1: 50, 2: 50, 3: 100} = ติ๊กทั้งสามช่องนี้ 50% ทุกครั้ง    
#   DEFAULT_RULE = {"mode": "checkbox_weighted", "weights": {1: 50, 2: 50, 3: 50}}
# 
#   ฟอร์ม Radio / Scale / ดาว -> สุ่มตาม % ที่กำหนดในทุกข้อ
#   DEFAULT_RULE = {"mode": "weighted", "weights": {0:10, 1:20,   # → สุ่มตาม % ที่กำหนด
#                                                   2:40, 3:20, 4:10}}
#
#   ปิด DEFAULT_RULE (สุ่มเต็ม 100% สำหรับข้อที่ไม่ระบุ):
#   DEFAULT_RULE = None


DEFAULT_RULE = None

# --- 1.7 Checkbox: จำนวนช่องที่สุ่มติ๊ก (กรณีไม่ได้ระบุ rule) ---
# สุ่มจำนวนช่องระหว่าง min–max
CHECKBOX_RANDOM_TICK_RANGE = (1, 3)

# --- 1.7 Delays ---
DELAY_BETWEEN_ACTIONS = 0.5  # วินาที — หน่วงระหว่างแต่ละคลิก
DELAY_BETWEEN_SUBMITS = 5  # วินาที — หน่วงระหว่างการส่งแต่ละครั้ง
PAGE_LOAD_TIMEOUT = 30  # วินาที — รอหน้าโหลดสูงสุด

# --- 1.8 Headless Mode ---
# True = ซ่อนหน้าต่าง Chrome (แนะนำให้ทดสอบด้วย False ก่อน)
HEADLESS = False


# ============================================================
# SECTION 2: GOOGLE LOGIN LOGIC
# ============================================================


def build_driver(headless: bool = False):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-background-networking")
    options.add_argument("--window-size=1280,800")
    # ลบ --single-process ออก ← ตัวการ crash
    options.binary_location = "/usr/bin/google-chrome"

    service = Service("/usr/local/bin/chromedriver")
    driver = webdriver.Chrome(options=options, service=service)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    return driver


def google_login(driver: uc.Chrome, email: str, password: str) -> bool:
    """
    Login Google account.
    ถ้าเจอ 2FA/CAPTCHA จะหยุดรอให้ทำด้วยตัวเองสูงสุด 60 วินาที
    คืนค่า True = สำเร็จ, False = ล้มเหลว
    """
    print(f"  [LOGIN] กำลัง login: {email}")
    try:
        driver.get("https://accounts.google.com/signin/v2/identifier")
        wait = WebDriverWait(driver, PAGE_LOAD_TIMEOUT)

        # ใส่อีเมล
        email_field = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='email']"))
        )
        email_field.clear()
        _human_type(email_field, email)
        time.sleep(0.5)
        wait.until(EC.element_to_be_clickable((By.ID, "identifierNext"))).click()
        time.sleep(DELAY_BETWEEN_ACTIONS)

        # ใส่รหัสผ่าน
        pw_field = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password']"))
        )
        pw_field.clear()
        _human_type(pw_field, password)
        time.sleep(0.5)
        wait.until(EC.element_to_be_clickable((By.ID, "passwordNext"))).click()
        time.sleep(DELAY_BETWEEN_ACTIONS * 2)

        # ตรวจ 2FA / challenge
        if any(
            kw in driver.current_url for kw in ["challenge", "2-step", "verification"]
        ):
            print(
                "  [LOGIN] ⚠️  พบ 2-Step Verification — กรุณายืนยันในหน้าต่างเบราว์เซอร์ (รอ 60 วิ)"
            )
            try:
                WebDriverWait(driver, 60).until(EC.url_contains("myaccount.google.com"))
                print("  [LOGIN] ✅ ยืนยันสำเร็จ")
            except TimeoutException:
                print("  [LOGIN] ❌ หมดเวลา — ข้ามบัญชีนี้")
                return False

        # ยืนยัน login สำเร็จ
        WebDriverWait(driver, 15).until(
            EC.any_of(
                EC.url_contains("myaccount.google.com"),
                EC.url_contains("google.com/"),
            )
        )
        print(f"  [LOGIN] ✅ Login สำเร็จ: {email}")
        return True

    except Exception as e:
        print(f"  [LOGIN] ❌ Exception: {e}")
        return False


def logout_and_clear(driver: uc.Chrome) -> None:
    """ล้าง cookies และ storage เพื่อ reset session อย่างสมบูรณ์"""
    print("  [LOGOUT] กำลังล้าง session...")
    try:
        driver.delete_all_cookies()
        driver.execute_script("window.localStorage.clear();")
        driver.execute_script("window.sessionStorage.clear();")
        time.sleep(1)
        print("  [LOGOUT] ✅ ล้างแล้ว")
    except Exception as e:
        print(f"  [LOGOUT] ⚠️  ล้างไม่สมบูรณ์: {e}")


def _human_type(element, text: str) -> None:
    """พิมพ์ทีละตัวอักษรพร้อม delay สุ่ม เพื่อเลียนแบบมนุษย์"""
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.05, 0.18))

def save_cookies(driver, email: str) -> None:
    """บันทึก cookie หลัง login สำเร็จ"""
    os.makedirs("cookies", exist_ok=True)
    filepath = f"cookies/{email}.json"
    with open(filepath, "w") as f:
        json.dump(driver.get_cookies(), f)
    print(f"  [COOKIE] ✅ บันทึก: {filepath}")


def load_cookies(driver, email: str) -> bool:
    """โหลด cookie แทนการ login — คืน True ถ้าสำเร็จ"""
    filepath = f"cookies/{email}.json"
    if not os.path.exists(filepath):
        return False
    try:
        driver.get("https://google.com")
        time.sleep(1)
        with open(filepath, "r") as f:
            for cookie in json.load(f):
                try:
                    driver.add_cookie(cookie)
                except:
                    pass
        driver.refresh()
        time.sleep(2)
        print(f"  [COOKIE] ✅ โหลด cookie: {email}")
        return True
    except Exception as e:
        print(f"  [COOKIE] ❌ โหลดไม่ได้: {e}")
        return False


def load_accounts(filepath="gmail_list.txt") -> list:
    """อ่านบัญชีจากไฟล์ gmail_list.txt"""
    accounts = []
    try:
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if not line or ":" not in line:
                    continue
                email, password = line.split(":", 1)
                accounts.append({
                    "email": email.strip(),
                    "password": password.strip()
                })
        print(f"  [ACCOUNTS] โหลดสำเร็จ: {len(accounts)} บัญชี")
    except FileNotFoundError:
        print(f"  [ACCOUNTS] ❌ ไม่พบไฟล์ {filepath}")
    return accounts

# ============================================================
# SECTION 3: DYNAMIC FORM FILLER LOGIC
# ============================================================

# ── ค่าคงที่ประเภทคำถาม ──
TYPE_RADIO = "radio"  # หลายตัวเลือก / สเกลเชิงเส้น / คะแนน
TYPE_CHECKBOX = "checkbox"  # ช่องทำเครื่องหมาย
TYPE_UNKNOWN = "unknown"  # ไม่รองรับ — ข้ามไป


# ─────────────────────────────────────────────────────────────
# 3A. Answer Rule Engine — แปลง ANSWER_RULES เป็น index ที่จะคลิก
# ─────────────────────────────────────────────────────────────


def resolve_radio_index(
    q_index: int, num_options: int, answer_rules: dict
) -> tuple[int, str]:
    """
    หา index ที่จะเลือกสำหรับคำถามประเภท radio (รวม scale และ rating)

    คืนค่า: (index_ที่เลือก, label_สำหรับ_print)

    รองรับทุก mode:
      fixed    → index ตายตัว
      range    → สุ่มในช่วง min–max (clamp ให้อยู่ใน options)
      weighted → สุ่มตาม % ที่กำหนด (normalize อัตโนมัติ ผลรวมไม่ต้อง = 100)
      ไม่ระบุ  → สุ่มเต็ม 100%
    """
    # ลำดับความสำคัญ: ANSWER_RULES[q_index] → DEFAULT_RULE → สุ่มเต็ม
    rule = answer_rules.get(q_index) or DEFAULT_RULE

    if rule is None:
        return random.randint(0, num_options - 1), "สุ่มเต็ม"

    mode = rule.get("mode", "")

    # ── fixed ──
    if mode == "fixed":
        val = rule.get("value", 0)
        if not isinstance(val, int) or not (0 <= val < num_options):
            print(f"    ⚠️  fixed value={val} เกินช่วง ({num_options} options) → สุ่มแทน")
            return random.randint(0, num_options - 1), "สุ่ม (fallback)"
        return val, f"Fixed → index {val}"

    # ── range ──
    if mode == "range":
        lo = max(0, rule.get("min", 0))
        hi = min(num_options - 1, rule.get("max", num_options - 1))
        if lo > hi:
            print(f"    ⚠️  range min={lo} > max={hi} → สุ่มทั้งหมดแทน")
            return random.randint(0, num_options - 1), "สุ่ม (fallback)"
        idx = random.randint(lo, hi)
        return idx, f"Range [{lo}–{hi}] → index {idx}"

    # ── weighted ──
    if mode == "weighted":
        weights_raw = rule.get("weights", {})
        # กรองเฉพาะ index ที่อยู่ใน range ที่ valid
        valid = {
            int(k): float(v)
            for k, v in weights_raw.items()
            if isinstance(k, int) and 0 <= int(k) < num_options and float(v) > 0
        }
        if not valid:
            print(f"    ⚠️  weighted ไม่มี weight ที่ valid → สุ่มทั้งหมดแทน")
            return random.randint(0, num_options - 1), "สุ่ม (fallback)"

        indices = list(valid.keys())
        weights = list(valid.values())
        idx = random.choices(indices, weights=weights, k=1)[0]

        # สร้าง label แสดง % จริง
        total = sum(weights)
        pct_str = ", ".join(
            f"index {i}={w / total * 100:.0f}%" for i, w in zip(indices, weights)
        )
        return idx, f"Weighted ({pct_str}) → index {idx}"

    # ── mode ไม่รู้จัก ──
    print(f"    ⚠️  mode='{mode}' ไม่รู้จัก → สุ่มทั้งหมดแทน")
    return random.randint(0, num_options - 1), "สุ่ม (fallback)"


def resolve_checkbox_indices(
    q_index: int, num_options: int, answer_rules: dict
) -> tuple[list, str]:
    """
    หา list ของ index ที่จะติ๊กสำหรับคำถามประเภท checkbox

    คืนค่า: ([index, ...], label_สำหรับ_print)

    รองรับ mode:
      checkbox_fixed    → ติ๊กตายตัวตาม list ที่กำหนด
      checkbox_weighted → แต่ละช่องมี % อิสระว่าจะถูกติ๊ก (คิดแยกกัน)
      fixed             → แปลงเป็น checkbox_fixed อัตโนมัติ (ถ้า value เป็น list)
      ไม่ระบุ           → สุ่มตาม CHECKBOX_RANDOM_TICK_RANGE
    """
    # ลำดับความสำคัญ: ANSWER_RULES[q_index] → DEFAULT_RULE → สุ่มเต็ม
    rule = answer_rules.get(q_index) or DEFAULT_RULE

    if rule is None:
        return _random_checkbox_indices(num_options), "สุ่มเต็ม"

    mode = rule.get("mode", "")

    # ── checkbox_fixed ──
    if mode in ("checkbox_fixed", "fixed"):
        raw = rule.get("values", rule.get("value", []))
        if isinstance(raw, int):
            raw = [raw]
        if not isinstance(raw, list):
            raw = []
        valid = [i for i in raw if isinstance(i, int) and 0 <= i < num_options]
        if not valid:
            print(f"    ⚠️  checkbox_fixed ไม่มี index valid → สุ่มแทน")
            return _random_checkbox_indices(num_options), "สุ่ม (fallback)"
        return valid, f"Checkbox Fixed → indices {[i + 1 for i in valid]}"

    # ── checkbox_weighted ──
    if mode == "checkbox_weighted":
        weights_raw = rule.get("weights", {})
        # แต่ละ index มี % อิสระ (ไม่รวมกัน)
        ticked = []
        detail_parts = []
        for k, pct in sorted(weights_raw.items()):
            idx = int(k)
            if not (0 <= idx < num_options):
                continue
            chance = float(pct) / 100.0
            rolled = random.random()
            hit = rolled < chance
            detail_parts.append(f"ช่อง{idx + 1}={pct}%→{'✓' if hit else '✗'}")
            if hit:
                ticked.append(idx)
        if not ticked:
            # ถ้าโชคร้ายไม่ติ๊กเลย → บังคับเลือก 1 ช่องที่มี weight สูงสุด
            best = max(weights_raw.items(), key=lambda x: float(x[1]))
            ticked = [int(best[0])]
            detail_parts.append(f"(บังคับ ช่อง{ticked[0] + 1} เพราะไม่มีช่องถูกเลือก)")
        label = f"Checkbox Weighted [{', '.join(detail_parts)}]"
        return ticked, label

    # ── mode ไม่รู้จัก ──
    print(f"    ⚠️  mode='{mode}' ไม่รู้จักสำหรับ checkbox → สุ่มแทน")
    return _random_checkbox_indices(num_options), "สุ่ม (fallback)"


def _random_checkbox_indices(num_options: int) -> list:
    """สุ่ม subset ของ checkbox indices ตาม CHECKBOX_RANDOM_TICK_RANGE"""
    lo = max(1, CHECKBOX_RANDOM_TICK_RANGE[0])
    hi = min(num_options, CHECKBOX_RANDOM_TICK_RANGE[1])
    count = random.randint(lo, hi)
    return random.sample(range(num_options), count)


# ─────────────────────────────────────────────────────────────
# 3B. Form loading & question discovery
# ─────────────────────────────────────────────────────────────


def load_form(driver: uc.Chrome, url: str) -> bool:
    """โหลดหน้าฟอร์ม คืนค่า True ถ้าโหลดสำเร็จ"""
    print(f"  [FORM] โหลดฟอร์ม: {url}")
    try:
        driver.get(url)
        WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "form"))
        )
        time.sleep(1.5)
        print("  [FORM] ✅ โหลดสำเร็จ")
        return True
    except TimeoutException:
        print("  [FORM] ❌ หมดเวลารอโหลดฟอร์ม")
        return False
    except Exception as e:
        print(f"  [FORM] ❌ Error: {e}")
        return False

def debug_form_structure(driver):
    """ดู role ทั้งหมดที่มีในหน้าฟอร์ม"""
    print("\n=== DEBUG: roles ที่พบในหน้า ===")
    
    # ดู role ทั้งหมด
    elements = driver.find_elements(By.CSS_SELECTOR, "[role]")
    role_counts = {}
    for el in elements:
        role = el.get_attribute("role")
        role_counts[role] = role_counts.get(role, 0) + 1
    
    for role, count in sorted(role_counts.items()):
        print(f"  role='{role}': {count} elements")
    
    print("\n=== DEBUG: container ที่น่าจะเป็นคำถาม ===")
    # ลองหา listitem / list
    for sel in ["[role='list']", "[role='listitem']", "[role='presentation']"]:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        if els:
            print(f"  {sel}: พบ {len(els)} elements")
    print("================================\n")

def detect_question_type(container) -> str:
    role = container.get_attribute("role") or ""
    if role == "radiogroup":
        return TYPE_RADIO
    if role == "group":
        if container.find_elements(By.CSS_SELECTOR, "[role='checkbox']"):
            return TYPE_CHECKBOX
    # ✅ เพิ่ม: รองรับ role='list' (Google Forms เวอร์ชันใหม่)
    if role == "list":
        if container.find_elements(By.CSS_SELECTOR, "[role='checkbox']"):
            return TYPE_CHECKBOX
        if container.find_elements(By.CSS_SELECTOR, "[role='radio']"):
            return TYPE_RADIO
    return TYPE_UNKNOWN


def discover_all_questions(driver: uc.Chrome) -> list:
    try:
        radio_els = driver.find_elements(By.CSS_SELECTOR, "[role='radiogroup']")
        checkbox_els = driver.find_elements(By.CSS_SELECTOR, "[role='group']")
        # ✅ เพิ่ม: ดึง role='list' ด้วย
        list_els = driver.find_elements(By.CSS_SELECTOR, "[role='list']")

        questions = []
        seen_ids = set()

        for el in radio_els + checkbox_els + list_els:
            q_type = detect_question_type(el)
            if q_type == TYPE_UNKNOWN or el.id in seen_ids:
                continue
            seen_ids.add(el.id)
            questions.append({"element": el, "type": q_type})

        # เรียงตามตำแหน่งบนหน้า
        questions.sort(key=lambda q: q["element"].location.get("y", 0))

        for i, q in enumerate(questions):
            q["index"] = i

        n_radio = sum(1 for q in questions if q["type"] == TYPE_RADIO)
        n_check = sum(1 for q in questions if q["type"] == TYPE_CHECKBOX)
        print(
            f"  [PARSER] พบ {len(questions)} คำถามที่รองรับ: "
            f"{n_radio} radio/scale/rating, {n_check} checkbox"
        )
        return questions

    except Exception as e:
        print(f"  [PARSER] ❌ Error: {e}")
        return []

# ─────────────────────────────────────────────────────────────
# 3C. Per-type click handlers
# ─────────────────────────────────────────────────────────────


def _safe_click(driver: uc.Chrome, element, label: str) -> bool:
    """คลิก element พร้อม scroll และ JS fallback"""
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", element
        )
        time.sleep(0.3)
        element.click()
        time.sleep(DELAY_BETWEEN_ACTIONS)
        return True
    except ElementClickInterceptedException:
        print(f"    ⚠️  คลิกถูกบล็อก ({label}) → ลอง JS click...")
        try:
            driver.execute_script("arguments[0].click();", element)
            time.sleep(DELAY_BETWEEN_ACTIONS)
            return True
        except Exception as e:
            print(f"    ❌ JS click ล้มเหลว ({label}): {e}")
            return False
    except Exception as e:
        print(f"    ❌ คลิก error ({label}): {e}")
        return False


def answer_radio(
    driver: uc.Chrome, q_index: int, container, answer_rules: dict
) -> bool:
    """
    ตอบคำถามประเภท radio (หลายตัวเลือก / สเกลเชิงเส้น / คะแนน)
    ใช้ resolve_radio_index() เพื่อหา index ตาม rule ที่กำหนด
    """
    options = container.find_elements(By.CSS_SELECTOR, "[role='radio']")
    if not options:
        print(f"  [Q{q_index + 1}][Radio] ⚠️  ไม่พบตัวเลือก — ข้าม")
        return False

    idx, label = resolve_radio_index(q_index, len(options), answer_rules)
    print(f"  [Q{q_index + 1}][Radio] {label} (จาก {len(options)} ตัวเลือก)")
    return _safe_click(driver, options[idx], f"Q{q_index + 1} option {idx + 1}")


def answer_checkbox(
    driver: uc.Chrome, q_index: int, container, answer_rules: dict
) -> bool:
    """
    ตอบคำถามประเภท checkbox (ช่องทำเครื่องหมาย)
    ใช้ resolve_checkbox_indices() เพื่อหา list ของ index ตาม rule
    ไม่คลิกซ้ำถ้าช่องนั้น checked อยู่แล้ว
    """
    options = container.find_elements(By.CSS_SELECTOR, "[role='checkbox']")
    if not options:
        print(f"  [Q{q_index + 1}][Checkbox] ⚠️  ไม่พบตัวเลือก — ข้าม")
        return False

    indices, label = resolve_checkbox_indices(q_index, len(options), answer_rules)
    print(
        f"  [Q{q_index + 1}][Checkbox] {label} "
        f"— ติ๊ก {len(indices)} จาก {len(options)} ช่อง"
    )

    ok_count = 0
    for idx in indices:
        cb = options[idx]
        if (cb.get_attribute("aria-checked") or "false").lower() != "true":
            if _safe_click(driver, cb, f"Q{q_index + 1} checkbox {idx + 1}"):
                ok_count += 1
        else:
            print(f"    ℹ️  ช่อง {idx + 1} ถูกติ๊กแล้ว — ข้าม")
            ok_count += 1

    return ok_count > 0


# ─────────────────────────────────────────────────────────────
# 3D. Orchestration & Submit
# ─────────────────────────────────────────────────────────────


def _click_submit(driver) -> bool:
    """
    กดปุ่ม ส่ง (Submit) หรือ ถัดไป (Next) โดยใช้คำสั่ง JavaScript ค้นหาจากทุกแท็กที่เป็นปุ่ม
    """
    print("  [SUBMIT] กำลังค้นหาปุ่มส่งแบบละเอียด...")

    try:
        js_script = """
        // ค้นหาจากทุกธาตุในหน้าเว็บที่มี role="button" (ไม่จำกัดแค่ div อีกต่อไป)
        var elements = document.querySelectorAll('[role="button"]');
        var clicked = false;

        for (var i = 0; i < elements.length; i++) {
            var text = (elements[i].textContent || elements[i].innerText || "").trim();

            // เช็คคำว่า ส่ง หรือ ถัดไป (ทั้งไทยและอังกฤษ)
            if (text === "ส่ง" || text === "Submit" || text === "ถัดไป" || text === "Next" || 
                text.includes("ส่ง") || text.includes("Submit") || text.includes("ถัดไป")) {

                // ป้องกันไม่ให้ไปกดปุ่ม 'ล้างแบบฟอร์ม' หรือ 'ย้อนกลับ' เด็ดขาด
                if (!text.includes("ล้าง") && !text.includes("Clear") && !text.includes("ย้อนกลับ") && !text.includes("Back")) {
                    elements[i].click();
                    clicked = true;
                    break;
                }
            }
        }
        return clicked;
        """

        clicked = driver.execute_script(js_script)

        if clicked:
            print("  [SUBMIT] ✅ เจอเป้าหมายและสั่งจิ้มปุ่มส่งเรียบร้อย!")
        else:
            print("  [SUBMIT] ❌ หาปุ่มส่งไม่เจอเลยจริงๆ")
            return False

    except Exception as e:
        print(f"  [SUBMIT] ❌ เกิดข้อผิดพลาดในการรันสคริปต์: {e}")
        return False

    # รอเช็คผลลัพธ์ว่า URL เปลี่ยนเป็นหน้าขอบคุณ (formResponse) หรือไม่
    print("  [SUBMIT] กำลังรอระบบบันทึกข้อมูลเข้า Google...")
    try:
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        # ถ้ายอดเข้าสำเร็จจริง URL ของหน้าเว็บต้องเปลี่ยนเป็นหน้า formResponse
        WebDriverWait(driver, 10).until(EC.url_contains("formResponse"))
        print("  [SUBMIT] ✅ ยอดขึ้นแน่นอน! ส่งฟอร์มสำเร็จจริง 100% 🎉")
        return True
    except:
        print("  [SUBMIT] ❌ ยอดไม่ขึ้น! หน้าฟอร์มไม่ยอมเปลี่ยนเป็นหน้าขอบคุณ")
        return False


def fill_and_submit_form(driver: uc.Chrome, answer_rules: dict) -> bool:
    """
    Pipeline หลัก:
      1. ค้นหาคำถามทั้งหมดในหน้า
      2. ส่งแต่ละคำถามไปยัง handler ที่ถูกต้องตามประเภท
      3. กด Submit
    """
    debug_form_structure(driver)
    questions = discover_all_questions(driver)
    if not questions:
        print("  [FORM] ❌ ไม่พบคำถามที่รองรับ — ยกเลิก")
        return False

    answered = 0
    for q in questions:
        q_index, q_type, container = q["index"], q["type"], q["element"]
        if q_type == TYPE_RADIO:
            ok = answer_radio(driver, q_index, container, answer_rules)
        elif q_type == TYPE_CHECKBOX:
            ok = answer_checkbox(driver, q_index, container, answer_rules)
        else:
            print(f"  [Q{q_index + 1}] ⚠️  ประเภทไม่รู้จัก '{q_type}' — ข้าม")
            ok = False
        if ok:
            answered += 1

    print(f"  [FORM] ตอบแล้ว {answered}/{len(questions)} ข้อ")
    return _click_submit(driver)


# ============================================================
# SECTION 4: MAIN EXECUTION BLOCK
# ============================================================


def run_mode_a_login(accounts: list, form_url: str, answer_rules: dict) -> None:
    total = len(accounts)
    print(f"\n{'=' * 60}")
    print(f"  MODE A — Login Submissions ({total} บัญชี)")
    print(f"{'=' * 60}\n")

    successful = 0
    failed = 0
    skipped = 0

    for i, account in enumerate(accounts, start=1):
        email = account["email"]
        print(f"\n--- บัญชี {i}/{total}: {email} ---")
        driver = None
        try:
            driver = build_driver(headless=HEADLESS)

            # ลองโหลด cookie ก่อน ถ้าไม่มีค่อย login
            logged_in = load_cookies(driver, email)
            if not logged_in:
                logged_in = google_login(driver, email, account["password"])
                if logged_in:
                    save_cookies(driver, email)

            if not logged_in:
                print("  ⏭️  ข้าม — login ล้มเหลว")
                skipped += 1
                continue

            if not load_form(driver, form_url):
                print("  ⏭️  ข้าม — โหลดฟอร์มไม่สำเร็จ")
                skipped += 1
                continue

            print(f"\n  กำลังส่งฟอร์ม บัญชี {i}/{total}...")
            result = fill_and_submit_form(driver, answer_rules)
            if result:
                successful += 1
            else:
                failed += 1

        except Exception as e:
            print(f"\n  ❌ Error บัญชี {i}/{total}: {e}")
            traceback.print_exc()
            failed += 1
        finally:
            if driver:
                driver.quit()
                print(f"  [BROWSER] ปิด browser บัญชี {i}/{total}")
                # ✅ เคลียร์ process ค้างอยู่
                import subprocess
                subprocess.run(["pkill", "-f", "chrome"], capture_output=True)
                time.sleep(2)

        if i < total:
            print(f"\n  ⏳ รอ {DELAY_BETWEEN_SUBMITS}s ก่อนบัญชีถัดไป...")
            time.sleep(DELAY_BETWEEN_SUBMITS)

    print(f"\n{'=' * 60}")
    print(f"  Mode A เสร็จสิ้น — {total} บัญชี")
    print(f"  ✅ สำเร็จ: {successful}  |  ❌ ล้มเหลว: {failed}  |  ⏭️  ข้าม: {skipped}")
    print(f"{'=' * 60}\n")


def run_mode_b_anonymous(loop_count: int, form_url: str, answer_rules: dict) -> None:
    """Mode B — 1 browser, ส่งซ้ำ loop_count ครั้ง, ล้าง cookie ระหว่างรอบ"""
    print(f"\n{'=' * 60}")
    print(f"  MODE B — Anonymous Submissions ({loop_count} ครั้ง)")
    print(f"{'=' * 60}\n")

    driver = None
    successful = 0
    failed = 0

    try:
        driver = build_driver(headless=HEADLESS)
        for i in range(1, loop_count + 1):
            print(f"\n--- ส่งครั้งที่ {i}/{loop_count} ---")
            try:
                if not load_form(driver, form_url):
                    print(f"  ⏭️  ข้ามครั้งที่ {i} — โหลดไม่สำเร็จ")
                    failed += 1
                    continue
                result = fill_and_submit_form(driver, answer_rules)
                if result:
                    successful += 1
                else:
                    failed += 1
                driver.delete_all_cookies()
            except Exception as e:
                print(f"\n  ❌ Error ครั้งที่ {i}: {e}")
                traceback.print_exc()
                failed += 1
            if i < loop_count:
                print(f"\n  ⏳ รอ {DELAY_BETWEEN_SUBMITS}s...")
                time.sleep(DELAY_BETWEEN_SUBMITS)

    except Exception as e:
        print(f"\n  ❌ Fatal browser error: {e}")
        traceback.print_exc()
    finally:
        if driver:
            driver.quit()
            print("\n  [BROWSER] ปิด browser แล้ว")

    print(f"\n{'=' * 60}")
    print(f"  Mode B เสร็จสิ้น")
    print(f"  ✅ สำเร็จ: {successful}  |  ❌ ล้มเหลว: {failed}  |  รวม: {loop_count}")
    print(f"{'=' * 60}\n")


def main():
    """Entry point — ตรวจสอบ config แล้วส่งต่อไปยัง mode ที่เลือก"""
    print("\n" + "=" * 60)
    print("  Google Forms Bot v3 — Smart Answer Modes  |  Starting...")
    print("=" * 60)

    if not FORM_URL or "YOUR_FORM_ID" in FORM_URL:
        print("\n  ❌ ERROR: กรุณาใส่ FORM_URL ที่ถูกต้องใน SECTION 1")
        return
    if LOGIN_REQUIRED and not ACCOUNTS:
        print("\n  ❌ ERROR: LOGIN_REQUIRED = True แต่ ACCOUNTS ว่างเปล่า")
        return
    if not LOGIN_REQUIRED and LOOP_COUNT < 1:
        print("\n  ❌ ERROR: LOOP_COUNT ต้องมากกว่า 0")
        return

    print(f"\n  Form URL      : {FORM_URL}")
    print(f"  Mode          : {'A (Login)' if LOGIN_REQUIRED else 'B (Anonymous)'}")
    print(
        f"  {'Accounts' if LOGIN_REQUIRED else 'Loop Count':<14}: "
        f"{len(ACCOUNTS) if LOGIN_REQUIRED else LOOP_COUNT}"
    )
    print(f"  Answer Rules  : {len(ANSWER_RULES)} ข้อที่กำหนดเฉพาะ")
    print(f"  Default Rule  : {DEFAULT_RULE if DEFAULT_RULE else 'ไม่ได้ตั้ง → สุ่มเต็ม'}")
    print(f"  Headless      : {HEADLESS}")

    if LOGIN_REQUIRED:
        run_mode_a_login(ACCOUNTS, FORM_URL, ANSWER_RULES)
    else:
        run_mode_b_anonymous(LOOP_COUNT, FORM_URL, ANSWER_RULES)


if __name__ == "__main__":
    main()
