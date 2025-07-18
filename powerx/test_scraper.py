from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
import os
import time
import logging
import pandas as pd
from django.utils import timezone

def scrape_data():
    """Scrape Excel from IEX using Google Chrome."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    # Setup paths
    current_dir = os.path.dirname(os.path.abspath(__file__))
    download_folder = os.path.join(current_dir, "IEX_Data") 
    if not os.path.exists(download_folder):
        os.makedirs(download_folder)

    # Chrome browser config
    options = Options()
    options.add_argument("--headless")  # Enable for background run
    options.add_argument("--disable-gpu")
    # options.add_argument("--no-sandbox")
    options.add_argument("--start-maximized")
    options.add_experimental_option("prefs", {
        "download.default_directory": download_folder,
        "download.prompt_for_download": False,
        "safebrowsing.enabled": True
    })

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        # Navigate to IEX
        driver.get("https://www.iexindia.com/market-data/green-day-ahead-market/market-snapshot")
        time.sleep(5)
        wait = WebDriverWait(driver, 20)

        # Step 2: Select "Tomorrow" in the delivery period dropdown
        dropdown = wait.until(EC.element_to_be_clickable((
            By.XPATH, "//div[contains(@aria-controls, 'R15alaackql')]"  # use partial match
        )))
        dropdown.click()

        print("✅ dropdown clicked!")
        time.sleep(2)

        tomorrow_option = wait.until(EC.element_to_be_clickable((By.XPATH, "//li[@data-value='TOMORROW']")))
        tomorrow_option.click()
        print("✅ 'Tomorrow' selected!")
        time.sleep(2)  # Give time for selection to process

        update_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Update Report']")))
        update_button.click()
        print("✅ 'Update Report' button clicked!")
        time.sleep(2)

        # Step 3: Click "Update Report"
        driver.find_element(By.XPATH, "//button[text()='Update Report']").click()
        time.sleep(3)

        # Click Export > Export Excel
        logging.info("Clicking export options...")
        driver.find_element(By.XPATH, "//button[contains(text(), 'Export')]").click()
        time.sleep(1)
        driver.find_element(By.XPATH, "//button[contains(text(), 'Export Excel')]").click()

        # Wait for file download
        file_downloaded = False
        timeout = time.time() + 60
        while not file_downloaded and time.time() < timeout:
            for file in os.listdir(download_folder):
                if file.endswith(".xlsx"):
                    new_name = f"IEX_Green_DAM_{timezone.now().strftime('%Y-%m-%d')}.xlsx"
                    os.rename(os.path.join(download_folder, file), os.path.join(download_folder, new_name))
                    logging.info(f"✅ File downloaded and renamed to {new_name}")
                    file_downloaded = True
                    break
            time.sleep(2)

        if not file_downloaded:
            logging.error("❌ File download failed or timed out.")

    except Exception as e:
        logging.error(f"⚠ Error occurred: {e}")
    finally:
        driver.quit()
        logging.info("🧹 Browser closed.")