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
from urllib.parse import quote
from typing import TYPE_CHECKING

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
INSTAMART_DB = os.getenv("INSTAMART_DB", "snapit_instamart")
INSTAMART_URI = os.getenv("INSTAMART_MONGO_URI", os.getenv("MONGO_URI", "mongodb://localhost:27017"))
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "scraped_instamart.json")
DEFAULT_LAT = float(os.getenv("INSTAMART_LAT", "12.9716"))
DEFAULT_LNG = float(os.getenv("INSTAMART_LNG", "77.5946"))
DEFAULT_LAT = os.getenv("INSTAMART_LAT", "12.9716")
DEFAULT_LNG = os.getenv("INSTAMART_LNG", "77.5946")


def scrape_instamart():
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

    # Allow geolocation (fake) to reduce location prompts
    try:
        driver.execute_cdp_cmd("Emulation.setGeolocationOverride", {
            "latitude": DEFAULT_LAT,
            "longitude": DEFAULT_LNG,
            "accuracy": 50
        })
    except Exception:
        pass
    scraped_results = []

    def set_location(pin: str = "560001"):
        """Attempt to set a deliverable Bangalore pin for Instamart."""
        try:
            # Try to click a location trigger if present
            triggers = driver.find_elements(By.XPATH, "//button[contains(.,'Deliver') or contains(.,'Change') or contains(.,'Location') or contains(.,'Add address')]")
            for trig in triggers:
                try:
                    driver.execute_script("arguments[0].click();", trig)
                    time.sleep(0.4)
                    break
                except Exception:
                    continue

            input_xpath = (
                "//input[contains(@placeholder,'location') or contains(@placeholder,'address') or"
                " contains(@aria-label,'location') or contains(@aria-label,'address') or"
                " contains(@name,'location') or contains(@name,'address')]"
            )
            loc_input = wait.until(EC.element_to_be_clickable((By.XPATH, input_xpath)))
            driver.execute_script("arguments[0].click();", loc_input)
            time.sleep(0.3)
            loc_input.send_keys(Keys.CONTROL + "a")
            loc_input.send_keys(Keys.BACKSPACE)
            loc_input.send_keys(pin)
            time.sleep(1.2)

            suggestions = driver.find_elements(By.XPATH, "//li|//div[contains(@class,'suggestion') or contains(@data-testid,'suggestion')]")
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

            print(f" Location set attempt done for pin {pin}")
        except Exception as e:
            print(f" Location set skipped/failed: {e}")

    def open_search(term: str):
        url = f"https://www.swiggy.com/instamart/search?query={quote(term)}&lat={DEFAULT_LAT}&lng={DEFAULT_LNG}"
        driver.get(url)
        print(f" Opened Instamart search URL: {url}")

    def save_to_mongo(records, collection_name: str):
        if not records:
            return
        try:
            inserted = mongo_client.save_records(records, collection_name=collection_name, db_name=INSTAMART_DB, uri=INSTAMART_URI)
            print(f" Saved {inserted} records to MongoDB collection '{collection_name}' in db '{INSTAMART_DB}'.")
        except Exception as e:
            print(f" MongoDB save failed for {collection_name}: {e}")

    try:
        driver.get(f"https://www.swiggy.com/instamart?lat={DEFAULT_LAT}&lng={DEFAULT_LNG}")
        print(" Instamart opened. Waiting for page to stabilize...")
        time.sleep(8)
        set_location("560001")

        print(f"🔍 Search terms this run: {PRODUCTS_TO_SEARCH}")

        for item in PRODUCTS_TO_SEARCH:
            term_results = []
            attempt = 0
            while attempt < 2:
                try:
                    print(f"Searching for: {item} (attempt {attempt+1})")
                    open_search(item)
                    time.sleep(6)

                    cards = wait.until(
                        EC.presence_of_all_elements_located(
                            (By.XPATH, "//div[contains(@data-testid,'item-card') or contains(@data-testid,'product-card') or contains(@class,'itemCard') or contains(@class,'product-card') or contains(@class,'_1ds9T')] | //a[contains(@href,'instamart')]")
                        )
                    )
                    print(f"   -> Found {len(cards)} result cards for {item}")

                    count = 0
                    for card in cards:
                        if count >= 5:
                            break
                        try:
                            name = ""
                            price = ""
                            quantity = ""
                            raw_text = card.text.strip()
                            href = None

                            try:
                                name_el = card.find_element(By.XPATH, ".//*[self::h3 or self::h4 or self::p][1]")
                                name = name_el.text.strip()
                            except Exception:
                                pass
                            try:
                                price_el = card.find_element(By.XPATH, ".//*[contains(text(),'₹')]")
                                price = price_el.text.strip()
                            except Exception:
                                pass
                            try:
                                qty_el = card.find_element(By.XPATH, ".//*[contains(text(),'g') or contains(text(),'kg') or contains(text(),'ml') or contains(text(),'l') or contains(text(),'pcs') or contains(text(),'pack')]")
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

                            row = {
                                "search_term": item,
                                "product_name": name,
                                "price": price,
                                "quantity": quantity,
                                "platform": "Instamart",
                                "location": "Bangalore",
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
                        save_to_mongo(term_results, collection_name=f"instamart_{item}")
                    break

                except TimeoutException:
                    print(f" Timed out waiting for results for {item} (attempt {attempt+1}). Taking a screenshot...")
                    driver.save_screenshot(f"instamart_timeout_{item}_a{attempt+1}.png")
                    attempt += 1
                    if attempt < 2:
                        driver.refresh()
                        time.sleep(3)
                        set_location("560001")
                        continue
                except Exception as e:
                    print(f" Error while scraping {item} (attempt {attempt+1}): {e}")
                    driver.save_screenshot(f"instamart_error_{item}_a{attempt+1}.png")
                    attempt += 1
                    if attempt < 2:
                        driver.refresh()
                        time.sleep(3)
                        set_location("560001")
                        continue

            if not term_results:
                print(f"   -> No Instamart results saved for {item}")

    finally:
        try:
            driver.quit()
        except OSError:
            pass

        if scraped_results:
            existing = []
            if os.path.exists(OUTPUT_FILE):
                try:
                    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                        existing = json.load(f) or []
                except Exception:
                    existing = []

            combined = existing + scraped_results
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(combined, f, indent=4, ensure_ascii=False)
            print(f"\n Data appended; total records now {len(combined)} in {OUTPUT_FILE}")
        else:
            print("\n No data captured. Check screenshots for UI changes.")

        print("\n Instamart session ended.")

if __name__ == "__main__":
    scrape_instamart()
