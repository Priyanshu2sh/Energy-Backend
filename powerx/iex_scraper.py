import logging
import time
from datetime import datetime
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from django.conf import settings

def scrape_data():

    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Define the path to the models folder
    download_folder = os.path.join(current_dir, "IEX_Data")
    logging.info(f"folder path {download_folder}")

    if not os.path.exists(download_folder):
        os.makedirs(download_folder)


    # Edge browser configuration
    options = Options()
    options.add_argument("--headless")  # ← Key: run browser without GUI
    options.add_argument("--disable-gpu")  # ← Prevent GPU-related crashes
    options.add_argument("--no-sandbox")  # Optional but often helpful
    options.add_argument("--start-maximized")

    if settings.ENVIRONMENT != 'local':
        # ✅ Set the actual Edge browser binary path here
        options.binary_location = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

    # Set download preferences
    options.add_experimental_option("prefs", {
        "download.default_directory": download_folder,   # Custom folder
        "download.prompt_for_download": False,
        "safebrowsing.enabled": True
    })

    # Path to msedgedriver.exe
    driver_path = os.path.join(current_dir, "msedgedriver.exe")
    logging.debug(f"driver path {driver_path}")
    # Verify if the driver exists
    if not os.path.exists(driver_path):
        logging.error(f"Edge driver not found at {driver_path}")
        raise FileNotFoundError(f"Edge driver not found at {driver_path}")

    logging.error(f"Path is correct at {driver_path}")
    service = Service(driver_path)

    # Initialize WebDriver for Edge
    driver = webdriver.Edge(service=service, options=options)

    try:
        logging.debug("Opening IEX Green Day Ahead Market snapshot page...")
        driver.get("https://www.iexindia.com/market-data/green-day-ahead-market/market-snapshot")
        time.sleep(5)  # Wait for the page to load

        # Find and click 'Export' button
        logging.info("Finding Export button...")
        export_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Export')]")
        export_button.click()
        logging.info("Clicked on Export button.")
        time.sleep(2)

        # Find and click 'Export Excel' button
        logging.info("Finding Export Excel button...")
        export_excel = driver.find_element(By.XPATH, "//button[contains(text(), 'Export Excel')]")
        export_excel.click()
        logging.info("Clicked on Export Excel button. File should be downloading.")

        # Wait for the file to download
        file_downloaded = False
        timeout = time.time() + 60  # 60 seconds timeout
        while not file_downloaded and time.time() < timeout:
            files = os.listdir(download_folder)
            
            # Rename the downloaded file with date-wise naming
            for file in files:
                if file.endswith(".xlsx"):
                    new_name = f"IEX_Green_DAM_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
                    os.rename(os.path.join(download_folder, file), os.path.join(download_folder, new_name))
                    logging.info(f"File downloaded and renamed to {new_name}")
                    file_downloaded = True
                    break

            time.sleep(2)

        if not file_downloaded:
            logging.error("File download timed out or failed.")

    except Exception as e:
        logging.error(f"An error occurred: {e}")

    finally:
        logging.info("Closing the browser...")
        driver.quit()