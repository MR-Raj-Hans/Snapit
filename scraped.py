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
import importlib
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

# Optional MongoDB settings (set environment variables to enable)
MONGO_URI = os.getenv("MONGO_URI", "")
# Default Zepto DB under the snapit connection
MONGO_DB = os.getenv("MONGO_DB", "snapit_zepto")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "prices")
ZEPTO_LOCATION = os.getenv("ZEPTO_LOCATION", "")
ZEPTO_LOCATIONS = [loc.strip() for loc in os.getenv("ZEPTO_LOCATIONS", "").split(",") if loc.strip()]
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "scraped_data.json")
MAX_RESULTS = int(os.getenv("ZEPTO_MAX_RESULTS", "12"))

def scrape_zepto():
    if not PRODUCTS_TO_SEARCH:
        print(" No search terms provided. Exiting without running browser.")
        return

    options = uc.ChromeOptions()
    # Adding a realistic user agent
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    # Pin to installed Chrome version to avoid mismatch
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
    wait = WebDriverWait(driver, 20) # This is our "patience" timer
    scraped_results = []

    def extract_image(element):
        """Pull the best image URL from a card if present."""
        try:
            img = element.find_element(By.XPATH, ".//img")
            for attr in ["src", "data-src", "data-srcset", "srcset"]:
                val = img.get_attribute(attr)
                if val:
                    # If srcset-style, take the first URL
                    if " " in val and "http" in val:
                        return val.split(" ")[0]
                    return val
        except Exception:
            return None
        return None

    def get_search_input():
        # Prefer a real input field first
        input_xpath = '//input[contains(@placeholder, "Search")] | //input[@type="text"]'
        try:
            return wait.until(EC.element_to_be_clickable((By.XPATH, input_xpath)))
        except TimeoutException:
            pass

        # Fall back to clicking a search trigger (if any), then re-find input
        trigger_xpath = '//span[contains(text(), "Search")]'
        triggers = wait.until(EC.presence_of_all_elements_located((By.XPATH, trigger_xpath)))
        for trigger in triggers:
            try:
                driver.execute_script("arguments[0].click();", trigger)
                time.sleep(1)
                return wait.until(EC.element_to_be_clickable((By.XPATH, input_xpath)))
            except Exception:
                continue

        raise TimeoutException("Search input not found")

    def try_set_location(location_text: str):
        """Location handling disabled; proceed with default site location."""
        print(" Skipping location selection (using site default).")

    def save_to_mongo(records, collection_name: str):
        if not records:
            return
        try:
            inserted = mongo_client.save_records(records, collection_name=collection_name, db_name=MONGO_DB)
            print(f" Saved {inserted} records to MongoDB collection '{collection_name}' in db '{MONGO_DB}'.")
        except Exception as e:
            print(f" MongoDB save failed for {collection_name}: {e}")

    try:
        driver.get("https://www.zeptonow.com/")
        print(" Website Opened. Waiting for page to stabilize...")
        time.sleep(10) # Give it extra time for the first load

        print(f"🔍 Search terms this run: {PRODUCTS_TO_SEARCH}")

        locations_to_test = [""]

        for location_text in locations_to_test:
            print("\n=== Using default/current location (no changes) ===")

            # Wait for search to be available before starting
            try:
                get_search_input()
            except TimeoutException:
                print("❌ Search input not found on initial load. Taking a screenshot...")
                driver.save_screenshot("search_input_not_found.png")
                continue

            for item in PRODUCTS_TO_SEARCH:
                term_results = []
                try:
                    print(f"Searching for: {item}")

                    search_box = get_search_input()

                    search_box.click()
                    time.sleep(1)

                    # Clear and Type
                    search_box.send_keys(Keys.CONTROL + "a")
                    search_box.send_keys(Keys.BACKSPACE)
                    search_box.send_keys(item)
                    search_box.send_keys(Keys.ENTER)

                    print(f"   Sent Enter for {item}, waiting for results...")
                    time.sleep(6) # Give the page a bit more time

                    # Extract top results for the current item
                    cards = wait.until(
                        EC.presence_of_all_elements_located(
                            (By.XPATH, '//a[contains(@href, "/pn/")]')
                        )
                    )
                    if len(cards) < MAX_RESULTS:
                        # Try a couple scrolls to load lazy cards
                        try:
                            for _ in range(2):
                                driver.execute_script("window.scrollBy(0, 600);")
                                time.sleep(1)
                                more = driver.find_elements(By.XPATH, '//a[contains(@href, "/pn/")]')
                                if len(more) > len(cards):
                                    cards = more
                                if len(cards) >= MAX_RESULTS:
                                    break
                        except Exception:
                            pass
                    print(f"   -> Found {len(cards)} result cards for {item}")

                    count = 0
                    for card in cards:
                        if count >= MAX_RESULTS:
                            break
                        try:
                            name = ""
                            price = ""
                            quantity = ""
                            raw_text = card.text.strip()
                            href = card.get_attribute("href")
                            image_url = extract_image(card)

                            try:
                                name = card.find_element(By.XPATH, './/h5').text.strip()
                            except Exception:
                                pass
                            try:
                                price = card.find_element(By.XPATH, './/h4[@data-testid="product-card-price"]').text.strip()
                            except Exception:
                                pass
                            try:
                                quantity = card.find_element(By.XPATH, './/span[@data-testid="product-card-quantity"]').text.strip()
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
                                        if any(unit in line.lower() for unit in ["kg", "g", "ml", "l", "pcs", "pack"]):
                                            quantity = line
                                            break
                                if not name and lines:
                                    candidate_lines = [
                                        line for line in lines
                                        if line.upper() != "ADD" and "₹" not in line
                                    ]
                                    if candidate_lines:
                                        name = max(candidate_lines, key=len)
                                    else:
                                        name = lines[0]

                            if (not name) or (quantity and name == quantity):
                                if href and "/pn/" in href:
                                    slug = href.split("/pn/")[1].split("/pvid/")[0]
                                    name = slug.replace("-", " ").strip()

                            row = {
                                "search_term": item,
                                "product_name": name,
                                "price": price,
                                "quantity": quantity,
                                "platform": "Zepto",
                                "location": location_text,
                                "url": href,
                                "image_url": image_url,
                                "raw_text": raw_text,
                            }
                            scraped_results.append(row)
                            term_results.append(row)
                            print(f"      + Scraped: {name or 'Unknown'}")
                            count += 1
                        except Exception:
                            continue

                    # Save per-term to its own collection
                    if term_results:
                        save_to_mongo(term_results, collection_name=item)

                except TimeoutException:
                    print(f" Timed out waiting for search box for {item}. Taking a screenshot...")
                    driver.save_screenshot(f"timeout_{item}.png")
                except Exception as e:
                    print(f"Could not search for {item}. Taking a screenshot to see why...")
                    driver.save_screenshot(f"error_{item}.png")
                    # This screenshot will tell us exactly what the bot was seeing!

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
        print("\n Session Ended.")

if __name__ == "__main__":
    scrape_zepto()