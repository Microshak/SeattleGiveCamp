def extract_urls(url):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from urllib.parse import urlparse, parse_qs, unquote
    import time

    options = Options()
    # options.add_argument("--headless")  # Try with headless disabled
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined})
        """
    })

    driver.get(url)
    time.sleep(5)

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'a[data-link_text="Visit Website Button"]'))
        )
        buttons = driver.find_elements(By.CSS_SELECTOR, 'a[data-link_text="Visit Website Button"]')
    except Exception as e:
        print("No buttons found:", e)
        buttons = []

    urls = []
    for button in buttons:
        href = button.get_attribute('href')
        if href:
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            if 'u' in qs:
                real_url = unquote(qs['u'][0])
                urls.append(real_url)

    driver.quit()
    return urls

if __name__ == "__main__":
    import requests

    base_url = "https://clutch.co/web-developers/seattle"
    page = 0
    all_urls = []

    while True:
        if page == 0:
            url = base_url
        else:
            url = f"{base_url}?page={page}"

        # Check if the page exists (404 detection)
        response = requests.get(url)
        if response.status_code == 404:
            print(f"Page {page} returned 404. Stopping.")
            break

        print(f"Scraping: {url}")
        urls = extract_urls(url)
        if not urls:
            print(f"No URLs found on page {page}.")
            break
        all_urls.extend(urls)
        print("page" + str(page))
        page += 1

    # Print all collected URLs
    for url in all_urls:
        print(url)