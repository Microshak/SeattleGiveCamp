import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os
from dotenv import load_dotenv
# Load contacts
contacts = pd.read_csv('linkedin_contacts.csv', header=0)

# Set up Selenium WebDriver (Chrome)
driver = webdriver.Chrome()  # Make sure chromedriver is installed and in PATH


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


load_dotenv()
username = os.getenv("LINKEDIN_USERNAME")
password = os.getenv("LINKEDIN_PASSWORD")

if not username or not password:
    print("[ERROR] LINKEDIN_USERNAME and LINKEDIN_PASSWORD must be set in your .env file.")
    

login_linkedin(driver, username, password)
        

for index, row in contacts.iterrows():
    profile_url = str(row['Profile URL']).strip('"')
    name = str(row['Name'])
    first_name = name.split()[0] if name and name != 'nan' else ''
    driver.get(profile_url)
    try:
        # Print all button aria-labels for debugging
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for btn in buttons:
            print("Button aria-label:", btn.get_attribute("aria-label"))
        if first_name:
            xpath = f"//button[contains(@aria-label, 'Message {first_name}')]"
        else:
            xpath = "//button[starts-with(@aria-label, 'Message')]"
        # Wait for the button to be clickable
        message_button = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        # Find all buttons with the correct aria-label
        buttons = driver.find_elements(By.XPATH, xpath)
        message_button = None
        for btn in buttons:
            if btn.is_displayed() and btn.is_enabled():
                message_button = btn
                break
        if not message_button:
            raise Exception("No visible and enabled message button found.")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", message_button)
        time.sleep(1)  # Give the UI a moment to update
        try:
            message_button.click()
        except Exception as e:
            print(f"[WARN] Standard click failed, trying JS click: {e}")
            driver.execute_script("arguments[0].click();", message_button)
        # Wait for the message box to appear
        textarea = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//div[contains(@role, 'textbox')]"))
        )
        textarea.send_keys("Hello world")
        print(f"Sent message to {profile_url}")
        time.sleep(2)
    except Exception as e:
        print(f"Could not message {profile_url}: {e}")

driver.quit()