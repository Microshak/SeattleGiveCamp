import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import os
from dotenv import load_dotenv

def login_linkedin(driver, username, password):
    driver.get("https://www.linkedin.com/login")
    time.sleep(2)
    email_elem = driver.find_element(By.ID, "username")
    pass_elem = driver.find_element(By.ID, "password")
    email_elem.send_keys(username)
    pass_elem.send_keys(password)
    pass_elem.send_keys(Keys.RETURN)
    time.sleep(3)
    print("[DEBUG] Logged into LinkedIn, landing page loaded.")

def get_contacts(driver, max_contacts=50):
    '''
    Uses LinkedIn search results filtered by location/network.
    Scrapes listed people and paginates if needed.
    Skips any usernames already found in linkedin_contacts.csv.
    '''
    contacts = []
    # Load processed usernames from CSV
    processed_usernames = set()
    out_file = "linkedin_contacts.csv"
    if os.path.exists(out_file):
        import csv
        with open(out_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                username = row.get("Username")
                if username:
                    processed_usernames.add(username)
    search_url = (
        "https://www.linkedin.com/search/results/people/?geoUrn=%5B%22103317020%22%2C%22103255706%22%2C%22104145663%22%2C%22103463944%22%2C%22103977389%22%2C%2290000091%22%2C%22104116203%22%5D&network=%5B%22F%22%5D&origin=FACETED_SEARCH"
    )
    driver.get(search_url)
    time.sleep(4)
    # Save search page for debugging if cards not found
    try:
        with open("search_debug.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print("[DEBUG] Saved search page HTML to search_debug.html for inspection.")
    except Exception as e:
        print(f"[ERROR] Could not write search_debug.html: {e}")
    total_scraped = 0

    while total_scraped < max_contacts:
        # New: Use LinkedIn's anti-scraping dynamic classnames workaround
        # Find all cards using data-chameleon-result-urn (most stable)
        people_cards = driver.find_elements(By.XPATH, "//div[@data-chameleon-result-urn]")
        print(f"[DEBUG] Found {len(people_cards)} people cards with data-chameleon-result-urn on current search page.")
        for card in people_cards:
            # --- Improved name extraction for robustness ---
            try:
                # First, try strict: <a> with /in/, grab span[aria-hidden]
                name_elem = card.find_element(By.XPATH, ".//a[contains(@href, '/in/')]//span[@aria-hidden='true']")
                name = name_elem.text.strip()
            except Exception:
                try:
                    # Fallback: get the <a> text content (sometimes includes extra, but good backup)
                    a_elem = card.find_element(By.XPATH, ".//a[contains(@href, '/in/')]")
                    name = a_elem.text.strip()
                except Exception:
                    name = ""
            try:
                # Location is in a <div> with t-normal and location-y class
                location_elem = card.find_element(By.XPATH, ".//div[contains(@class, 't-normal') and contains(@class, 'AfYWBcJALseTYlgAgWShDEAOnbbteeRp')]")
                location = location_elem.text.strip()
            except Exception:
                location = ""
            try:
                profile_anchor = card.find_element(By.XPATH, ".//a[contains(@href, '/in/') and @data-test-app-aware-link]")
                profile_url = profile_anchor.get_attribute("href")
                # Clean up tracking params etc
                if profile_url:
                    profile_url = profile_url.split("?")[0]
                username = ""
                u = profile_url.split("/in/")
                if len(u) > 1:
                    username = u[1].split("/")[0].split("?")[0]
            except Exception:
                profile_url = ""
                username = ""
            if not name or not profile_url or not username or username in processed_usernames:
                continue
            contacts.append({
                "name": name,
                "location": location,
                "profile_url": profile_url,
                "username": username
            })
            total_scraped += 1
            if total_scraped >= max_contacts:
                break

        # Check for and click "Next" pagination button if more profiles needed
        if total_scraped < max_contacts:
            try:
                next_btn = driver.find_element(By.XPATH, "//button[contains(@aria-label,'Next')]")
                if next_btn.is_enabled():
                    driver.execute_script("arguments[0].scrollIntoView();", next_btn)
                    time.sleep(1)
                    next_btn.click()
                    time.sleep(3)
                else:
                    break
            except Exception:
                break  # No more pages

    return contacts

def get_profile_info(driver, profile_url):
    """
    Visits profile and extracts: name, location, username, headline, email.
    """
    info = {"profile_url": profile_url, "name": "", "location": "", "username": "", "headline": "", "email": ""}
    try:
        driver.get(profile_url)
        time.sleep(2)
        # Name
        try:
            name_elem = driver.find_element(By.CSS_SELECTOR, "h1.text-heading-xlarge")
            info["name"] = name_elem.text.strip()
        except Exception:
            pass
        # Location
        try:
            loc_elem = driver.find_element(By.CSS_SELECTOR, "span.text-body-small.inline.t-black--light.break-words")
            info["location"] = loc_elem.text.strip()
        except Exception:
            pass
        # Headline
        try:
            headline_elem = driver.find_element(By.CSS_SELECTOR, "div.text-body-medium.break-words")
            info["headline"] = headline_elem.text.strip()
        except Exception:
            pass
        # Username from URL
        try:
            # Should be after '/in/' but before '?'
            u = profile_url.split("/in/")
            if len(u) > 1:
                username = u[1].split("/")[0].split("?")[0]
                info["username"] = username
        except Exception:
            pass
        # Email extraction
        try:
            contact_info_btn = driver.find_element(By.XPATH, "//a[contains(@href, '/overlay/contact-info/')]")
            driver.execute_script("arguments[0].click();", contact_info_btn)
            time.sleep(2)
            # --- Attempt to read name from the modal <h1 id="pv-contact-info"> if present ---
            try:
                h1_contact = driver.find_element(By.ID, "pv-contact-info")
                modal_name = h1_contact.text.strip()
                if modal_name:
                    info["name"] = modal_name
            except Exception:
                pass
            mail_elems = driver.find_elements(By.XPATH, "//a[starts-with(@href, 'mailto:')]")
            if mail_elems:
                info["email"] = mail_elems[0].text.strip()
            # Close the modal if possible
            try:
                close_btn = driver.find_element(By.XPATH, "//button[@aria-label='Dismiss']")
                close_btn.click()
            except Exception:
                pass
        except Exception:
            pass
    except Exception as e:
        print(f"Failed to scrape profile {profile_url}: {e}")
    return info

def main():
    print("LinkedIn Contacts Scraper")
    options = webdriver.ChromeOptions()
    # Comment out headless mode for debugging
    # options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1280,800')
    print("[DEBUG] Attempting to launch ChromeDriver...")
    driver = None
    try:
        driver_path = ChromeDriverManager().install()
        print(f"[DEBUG] ChromeDriver path: {driver_path}")
        driver = webdriver.Chrome(service=Service(driver_path), options=options)
    except Exception as e:
        print(f"[ERROR] Failed to launch Chrome browser: {e}")
        print("Ensure Google Chrome and compatible ChromeDriver are installed. Try updating Chrome and running 'pip install --upgrade selenium webdriver-manager'.")
        return

    try:
        # Load .env variables
        load_dotenv()
        username = os.getenv("LINKEDIN_USERNAME")
        password = os.getenv("LINKEDIN_PASSWORD")

        if not username or not password:
            print("[ERROR] LINKEDIN_USERNAME and LINKEDIN_PASSWORD must be set in your .env file.")
            return

        login_linkedin(driver, username, password)
        contacts = get_contacts(driver, max_contacts=500)  # Increased max, but will limit processed per run
        print(f"Found {len(contacts)} contacts. Filtering and processing...")

        # Load already processed profile URLs
        out_file = "linkedin_contacts.csv"
        processed_urls = set()
        if os.path.exists(out_file):
            import csv
            with open(out_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    url = row.get("Profile URL")
                    if url:
                        processed_urls.add(url)

        # Filter out any contacts already in the CSV, ensuring 0 duplicate viewing/scraping
        to_process_contacts = [c for c in contacts if c["profile_url"] not in processed_urls]

        # Save header if file is new/empty
        if not os.path.exists(out_file) or os.stat(out_file).st_size == 0:
            with open(out_file, "w", encoding="utf-8") as f:
                f.write("Name,Location,Profile URL,Username,Headline,Email\n")

        max_profiles = 50
        contacts_processed = 0
        for c in to_process_contacts:
            if contacts_processed >= max_profiles:
                print("Daily profile view limit reached (50). You can run the script again tomorrow for more.")
                break
            print(f"Visiting profile: {c['profile_url']}")
            profile_info = get_profile_info(driver, c["profile_url"])
            # Save immediately
            with open(out_file, "a", encoding="utf-8") as f:
                f.write(
                    f'"{profile_info.get("name","")}",'
                    f'"{profile_info.get("location","")}",'
                    f'"{profile_info.get("profile_url","")}",'
                    f'"{profile_info.get("username","")}",'
                    f'"{profile_info.get("headline","")}",'
                    f'"{profile_info.get("email","")}"\n'
                )
            processed_urls.add(c["profile_url"])
            contacts_processed += 1
            print(f"Saved: {profile_info.get('name','')} ({profile_info.get('location','')})")
        print(f"Contacts exported/updated in {out_file} (processed {contacts_processed} today)")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    main()
