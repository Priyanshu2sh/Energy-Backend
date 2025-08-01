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
from datetime import datetime

def process_excel_file(download_folder):
    """Load and preview the downloaded Excel file."""
    file_name = f"IEX_Green_DAM_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    file_path = os.path.join(download_folder, file_name)

    if os.path.exists(file_path):
        df = pd.read_excel(file_path)
        print("✅ File loaded successfully:")
        print(df.head())
    else:
        print("❌ File not found!")

def scrape_data():
    """Scrape Excel from IEX using headless Google Chrome."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    # Setup paths
    current_dir = os.path.dirname(os.path.abspath(__file__))
    download_folder = os.path.join(current_dir, "IEX_Data")
    if not os.path.exists(download_folder):
        os.makedirs(download_folder)

    # Chrome browser config
    options = Options()
    options.add_argument("--headless=new")  # Use `--headless=new` for Chrome v109+
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_experimental_option("prefs", {
        "download.default_directory": download_folder,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    })

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.get("https://www.iexindia.com/market-data/green-day-ahead-market/market-snapshot")
        print("✅ Page found!")
        wait = WebDriverWait(driver, 15)

        # Click the dropdown
        dropdown = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@aria-controls, 'R15alaackql')]")))
        driver.execute_script("arguments[0].click();", dropdown)
        print("✅ Dropdown clicked!")
        time.sleep(2)

        # Select 'Tomorrow'
        tomorrow_option = wait.until(EC.element_to_be_clickable((By.XPATH, "//li[@data-value='TOMORROW']")))
        driver.execute_script("arguments[0].click();", tomorrow_option)
        print("✅ 'Tomorrow' selected!")
        time.sleep(2)

        # Click 'Update Report'
        update_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Update Report']")))
        driver.execute_script("arguments[0].click();", update_button)
        print("✅ 'Update Report' button clicked!")
        time.sleep(2)

        # Click Export → Export Excel
        export_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Export')]")))
        driver.execute_script("arguments[0].click();", export_button)
        time.sleep(1)
        export_excel = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Export Excel')]")))
        driver.execute_script("arguments[0].click();", export_excel)

        # Wait for file download
        logging.info("⏳ Waiting for Excel download...")
        file_downloaded = False
        timeout = time.time() + 60

        while not file_downloaded and time.time() < timeout:
            for file in os.listdir(download_folder):
                if file.endswith(".xlsx") and not file.endswith(".crdownload"):
                    new_name = f"IEX_Green_DAM_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
                    old_path = os.path.join(download_folder, file)
                    new_path = os.path.join(download_folder, new_name)

                    if os.path.exists(new_path):
                        os.remove(new_path)
                    os.rename(old_path, new_path)
                    logging.info(f"✅ File downloaded and renamed to {new_name}")
                    file_downloaded = True
                    break
            time.sleep(2)

        if not file_downloaded:
            logging.error("❌ File download failed or timed out.")
        else:
            process_excel_file(download_folder)

    except Exception as e:
        logging.error(f"⚠️ Error occurred: {e}")
    finally:
        driver.quit()
        logging.info("🧹 Browser closed.")

# Run the script
# if __name__ == "__main__":
#     scrape_data()
