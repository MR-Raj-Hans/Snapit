import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
import json
import os
from typing import TYPE_CHECKING
from urllib.parse import quote, urljoin

import mongo_client

if TYPE_CHECKING:
    from pymongo import MongoClient  # pragma: no cover

def load_search_terms():
    """Load search terms from SEARCH_TERMS env (comma/newline-separated), search_terms.txt, or CLI args. No defaults."""
    env_terms = os.getenv("SEARCH_TERMS", "").strip()
    if env_terms:
        terms = [part.strip() for part in env_terms.replace("\n", ",").split(",") if part.strip()]
        if terms:
            print(f"🔧 Using search terms from SEARCH_TERMS env: {terms}")
            return terms

    terms_file = os.getenv("SEARCH_TERMS_FILE", "search_terms.txt")
    if os.path.exists(terms_file):
        try:
            with open(terms_file, "r", encoding="utf-8") as fh:
                raw = fh.read()
            candidates = [part.strip() for part in raw.replace("\n", ",").split(",") if part.strip()]
            if candidates:
                print(f"Using search terms from {terms_file}: {candidates}")
                return candidates
        except Exception as e:
            print(f"Could not read {terms_file}: {e}")

    if len(sys.argv) > 1:
        arg_terms = " ".join(sys.argv[1:]).strip()
        if arg_terms:
            print(f"🔧 Using search term from CLI args: {arg_terms}")
            return [arg_terms]

    print(" No search terms provided. Set SEARCH_TERMS env, add to search_terms.txt, or pass a term as an argument.")
    return []

PRODUCTS_TO_SEARCH = load_search_terms()
BLINKIT_DB = os.getenv("BLINKIT_DB", "snapit_blinkit")
BLINKIT_URI = os.getenv("BLINKIT_MONGO_URI", os.getenv("MONGO_URI", "mongodb://localhost:27017"))
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "scraped_blinkit.json")
MAX_RESULTS = int(os.getenv("BLINKIT_MAX_RESULTS", "12"))
DEFAULT_LAT = float(os.getenv("BLINKIT_LAT", "12.9716"))
DEFAULT_LNG = float(os.getenv("BLINKIT_LNG", "77.5946"))

def scrape_blinkit():
    if not PRODUCTS_TO_SEARCH:
        print(" No search terms provided. Exiting without running browser.")
        return

    options = uc.ChromeOptions()
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option('prefs', {
        'profile.default_content_setting_values.geolocation': 1,
    })
    if os.getenv("HEADLESS", "1") != "0":
        options.add_argument('--headless=new')

    driver = None
    try:
        driver = uc.Chrome(options=options, version_main=144)
    except Exception as e:
        try:
            import traceback
            print("DRIVER_INIT_FAILED (retry without pin)", e)
            traceback.print_exc()
            driver = uc.Chrome(options=options)
        except Exception as e2:
            print("DRIVER_INIT_FAILED final", e2)
            import traceback
            traceback.print_exc()
            return

    wait = WebDriverWait(driver, 25)
    scraped_results = []

    def extract_product_url(element, product_name: str = ""):
        """Attempt to pull a product URL from the element, its children, or ancestors."""
        base = "https://www.blinkit.com"
        candidates = []

        direct_href = element.get_attribute("href")
        if direct_href:
            candidates.append(direct_href)

        for attr in ["data-pf", "data-href", "data-url", "data-link"]:
            val = element.get_attribute(attr)
            if val:
                candidates.append(val)

        # Walk up a few ancestors to catch data-* on parent containers
        parent = element
        for _ in range(3):
            try:
                parent = parent.find_element(By.XPATH, "..")
            except Exception:
                break
            for attr in ["data-pf", "data-href", "data-url", "data-link"]:
                val = parent.get_attribute(attr)
                if val:
                    candidates.append(val)

        try:
            anchors = element.find_elements(By.XPATH, ".//a[@href]")
            for a in anchors:
                href = a.get_attribute("href")
                if href:
                    candidates.append(href)
        except Exception:
            pass

        for href in candidates:
            if href.startswith("http"):
                return href
            if href.startswith("/"):
                return urljoin(base, href)
        if product_name:
            return f"{base}/s/?q={quote(product_name)}"
        return None

    def set_location(pin: str = "560001"):
        """Handle Blinkit location modal: open, enter pin, select suggestion, confirm, wait for dialog to close."""
        try:
            # Open the location dialog/button if present
            triggers = driver.find_elements(
                By.XPATH,
                "//button[contains(.,'Deliver') or contains(.,'Change') or contains(.,'Location') or contains(.,'Add address')]"
            )
            for trig in triggers:
                try:
                    driver.execute_script("arguments[0].click();", trig)
                    time.sleep(0.5)
                    break
                except Exception:
                    continue

            input_xpath = (
                "//input[contains(@placeholder,'address') or contains(@placeholder,'location') or"
                " contains(@aria-label,'address') or contains(@aria-label,'location') or"
                " contains(@name,'location') or contains(@name,'address')]"
            )
            loc_input = wait.until(EC.element_to_be_clickable((By.XPATH, input_xpath)))
            driver.execute_script("arguments[0].click();", loc_input)
            time.sleep(0.3)
            loc_input.send_keys(Keys.CONTROL + "a")
            loc_input.send_keys(Keys.BACKSPACE)
            loc_input.send_keys(pin)
            time.sleep(1.2)

            suggestions = driver.find_elements(By.XPATH, "//li | //div[contains(@data-testid,'suggestion') or contains(@class,'suggestion')]")
            if suggestions:
                driver.execute_script("arguments[0].click();", suggestions[0])
                time.sleep(1.0)
            else:
                loc_input.send_keys(Keys.ENTER)
                time.sleep(1.0)

            buttons = driver.find_elements(By.XPATH, "//button[contains(.,'Deliver') or contains(.,'Continue') or contains(.,'Save') or contains(.,'Confirm')]")
            for btn in buttons:
                try:
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(0.8)
                    break
                except Exception:
                    continue

            # Wait briefly for any dialog to disappear
            try:
                WebDriverWait(driver, 8).until(EC.invisibility_of_element_located((By.XPATH, "//div[contains(@role,'dialog') or contains(@class,'modal')]") ))
            except Exception:
                pass

            print(f" Location set attempt done for pin {pin}")
        except Exception as e:
            print(f" Location set skipped/failed: {e}")

    # Allow geolocation (fake) to reduce location prompts
    try:
        driver.execute_cdp_cmd("Emulation.setGeolocationOverride", {
            "latitude": DEFAULT_LAT,
            "longitude": DEFAULT_LNG,
            "accuracy": 50
        })
    except Exception:
        pass

    def handle_location_modal(pin: str = "560001"):
        """If a location modal is present, attempt detect or enter pin and close it."""
        try:
            dialog = driver.find_elements(By.XPATH, "//div[contains(@role,'dialog') or contains(@class,'modal')]")
            if not dialog:
                return

            detect_btn = driver.find_elements(By.XPATH, "//button[contains(.,'Detect my location')] | //button[contains(.,'Detect')]")
            if detect_btn:
                try:
                    driver.execute_script("arguments[0].click();", detect_btn[0])
                    WebDriverWait(driver, 8).until(EC.invisibility_of_element_located((By.XPATH, "//div[contains(@role,'dialog') or contains(@class,'modal')]") ))
                    print(" Location modal closed via detect.")
                    return
                except Exception:
                    pass

            loc_input = None
            try:
                loc_input = driver.find_element(By.XPATH, "//input[contains(@placeholder,'delivery location') or contains(@placeholder,'location') or contains(@aria-label,'location')]")
            except Exception:
                pass
            if loc_input:
                driver.execute_script("arguments[0].click();", loc_input)
                time.sleep(0.3)
                loc_input.send_keys(Keys.CONTROL + "a")
                loc_input.send_keys(Keys.BACKSPACE)
                loc_input.send_keys(pin)
                time.sleep(1.0)
                loc_input.send_keys(Keys.ENTER)
                time.sleep(1.0)
                # pick first suggestion if present
                suggestions = driver.find_elements(By.XPATH, "//li | //div[contains(@data-testid,'suggestion') or contains(@class,'suggestion')]")
                if suggestions:
                    driver.execute_script("arguments[0].click();", suggestions[0])
                    time.sleep(0.8)
                confirm = driver.find_elements(By.XPATH, "//button[contains(.,'Deliver') or contains(.,'Confirm') or contains(.,'Continue')]")
                for btn in confirm:
                    try:
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(0.6)
                        break
                    except Exception:
                        continue
                try:
                    WebDriverWait(driver, 8).until(EC.invisibility_of_element_located((By.XPATH, "//div[contains(@role,'dialog') or contains(@class,'modal')]") ))
                    print(" Location modal closed via pin.")
                except Exception:
                    pass
        except Exception as e:
            print(f" Location modal handling skipped: {e}")

    def open_search(term: str):
        url = f"https://www.blinkit.com/s/?q={quote(term)}"
        driver.get(url)
        print(f" Opened search URL: {url}")

    def save_to_mongo(records, collection_name: str):
        if not records:
            return
        try:
            inserted = mongo_client.save_records(records, collection_name=collection_name, db_name=BLINKIT_DB, uri=BLINKIT_URI)
            print(f" Saved {inserted} records to MongoDB collection '{collection_name}' in db '{BLINKIT_DB}'.")
        except Exception as e:
            print(f" MongoDB save failed for {collection_name}: {e}")

    try:
        driver.get("https://www.blinkit.com/")
        print(" Blinkit opened. Waiting for page to stabilize...")
        time.sleep(6)

        print(f"🔍 Search terms this run: {PRODUCTS_TO_SEARCH}")

        for item in PRODUCTS_TO_SEARCH:
            term_results = []
            try:
                print(f"Searching for: {item}")
                open_search(item)
                time.sleep(6)
                handle_location_modal()
                time.sleep(3)

                if os.getenv("DUMP_HTML"):
                    try:
                        with open(f"blinkit_{item}_page.html", "w", encoding="utf-8") as fh:
                            fh.write(driver.page_source)
                        print(f" Saved page HTML to blinkit_{item}_page.html for inspection.")
                    except Exception as e:
                        print(f" Could not dump HTML: {e}")
                card_xpath = (
                    "//*[@id='product_container']/following::div[@role='button'][.//div[normalize-space()='ADD']]"
                    " | //div[@role='button'][.//div[normalize-space()='ADD'] and @data-pf]"
                )
                try:
                    cards = wait.until(
                        EC.presence_of_all_elements_located(
                            (By.XPATH, card_xpath)
                        )
                    )
                except TimeoutException:
                    cards = driver.find_elements(By.XPATH, card_xpath)

                # Scroll multiple times to load more if we found too few
                scroll_attempts = 0
                while len(cards) < MAX_RESULTS and scroll_attempts < 6:
                    try:
                        driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
                        time.sleep(1.5)
                        more_cards = driver.find_elements(By.XPATH, card_xpath)
                        if len(more_cards) > len(cards):
                            cards = more_cards
                        else:
                            scroll_attempts += 1
                    except Exception:
                        break
                # If we still only have a container, fall back to ancestors of ADD buttons
                if len(cards) <= 1:
                    add_cards = driver.find_elements(
                        By.XPATH,
                        "//button[contains(.,'ADD')]/ancestor::*[self::article or self::div or self::li][1]"
                    )
                    if add_cards:
                        cards = add_cards

                print(f"   -> Found {len(cards)} result cards for {item}")

                count = 0
                for card in cards:
                    if count >= MAX_RESULTS:
                        break
                    try:
                        target = card
                        if card.tag_name.lower() == "button":
                            try:
                                target = card.find_element(By.XPATH, "ancestor::*[self::article or self::div or self::li][1]")
                            except Exception:
                                target = card
                        name = ""
                        price = ""
                        quantity = ""
                        raw_text = target.text.strip()
                        href = extract_product_url(target, name or item)

                        try:
                            name_el = target.find_element(By.XPATH, ".//*[self::h3 or self::h4 or self::p][1]")
                            name = name_el.text.strip()
                        except Exception:
                            pass
                        try:
                            price_el = target.find_element(By.XPATH, ".//*[contains(text(),'₹')]")
                            price = price_el.text.strip()
                        except Exception:
                            pass
                        try:
                            qty_el = target.find_element(By.XPATH, ".//*[contains(text(),'g') or contains(text(),'kg') or contains(text(),'ml') or contains(text(),'l') or contains(text(),'pcs') or contains(text(),'pack')]")
                            quantity = qty_el.text.strip()
                        except Exception:
                            pass

                        if raw_text:
                            lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
                            if not price:
                                for line in lines:
                                    if "₹" in line:
                                        price = line
                                        break
                            if not quantity:
                                for line in lines:
                                    low = line.lower()
                                    if any(unit in low for unit in ["kg", "g", "ml", "l", "pcs", "pack"]):
                                        quantity = line
                                        break
                            if not name and lines:
                                candidate_lines = [line for line in lines if line.upper() != "ADD" and "₹" not in line]
                                if candidate_lines:
                                    name = max(candidate_lines, key=len)
                                else:
                                    name = lines[0]

                        if not price:
                            # Skip placeholders/skeleton cards without price
                            continue
                        if name.strip().upper() == "ADD":
                            continue

                        row = {
                            "search_term": item,
                            "product_name": name,
                            "price": price,
                            "quantity": quantity,
                            "platform": "Blinkit",
                            "location": "",
                            "url": href,
                            "raw_text": raw_text,
                        }
                        scraped_results.append(row)
                        term_results.append(row)
                        print(f"      + Scraped: {name or 'Unknown'}")
                        count += 1
                    except Exception:
                        continue

                if term_results:
                    save_to_mongo(term_results, collection_name=f"blinkit_{item}")

            except TimeoutException:
                print(f" Timed out waiting for results for {item}. Taking a screenshot...")
                driver.save_screenshot(f"blinkit_timeout_{item}.png")
            except Exception as e:
                print(f" Error while scraping {item}: {e}")
                driver.save_screenshot(f"blinkit_error_{item}.png")

    finally:
        try:
            driver.quit()
        except OSError:
            pass

        if scraped_results:
            def _clean(rows):
                for r in rows:
                    if '_id' in r and not isinstance(r['_id'], str):
                        try:
                            r['_id'] = str(r['_id'])
                        except Exception:
                            r['_id'] = None
                return rows

            existing = []
            if os.path.exists(OUTPUT_FILE):
                try:
                    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                        existing = json.load(f) or []
                except Exception:
                    existing = []

            combined = _clean(existing) + _clean(scraped_results)
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(combined, f, indent=4, ensure_ascii=False)
            print(f"\n Data appended; total records now {len(combined)} in {OUTPUT_FILE}")
        else:
            print("\n No data captured. Check screenshots for UI changes.")

        print("\n Blinkit session ended.")

if __name__ == "__main__":
    scrape_blinkit()
