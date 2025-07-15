import os
from accounts.models import User
from celery import shared_task
from powerx.AI_Model.model_scheduling import run_models_sequentially
from powerx.current_day_scraper import scrape_current_data
from powerx.test_scraper import scrape_data
from django.core.mail import send_mail
from energy_transition import settings
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
from datetime import datetime
import logging
import pandas as pd
from powerx.models import CleanData
from django.db import IntegrityError
import traceback
from django.utils import timezone
import logging
logger = logging.getLogger(__name__)

# Get the logger that is configured in the settings
traceback_logger = logging.getLogger('django')

@shared_task(bind=True)
def run_model_task(self):
    start_time = datetime.now()
    try:
        # Run the scraping script
        run_models_sequentially()
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Log success message
        logging.info(f"Prediction Task executed successfully in {duration:.2f} seconds.")
        return "Prediction Task executed successfully"

    except Exception as e:
        # Log any errors
        logging.error(f"Prediction Task failed with error: {str(e)}")
        tb = traceback.format_exc()  # Get the full traceback
        traceback_logger.error(f"Exception: {str(e)}\nTraceback:\n{tb}")  # Log error with traceback
        return f"Prediction Task failed: {str(e)}"

# Column mapping dictionary
COLUMN_MAPPING = {
    'Date': 'date',
    'Hour': 'hour',
    'Purchase Bid (MW)': 'purchase_bid',
    'Total Sell Bid (MW)': 'total_sell_bid',
    'Solar Bid (MW)': 'sell_bid_solar',
    'Non-Solar Sell Bid (MW)': 'sell_bid_non_solar',
    'Hydro Sell Bid (MW)': 'sell_bid_hydro',
    'Total MCV (MW)': 'mcv_total',
    'Solar MCV (MW)': 'mcv_solar',
    'Non-Solar MCV (MW)': 'mcv_non_solar',
    'Hydro MCV (MW)': 'mcv_hydro',
    'MCP (Rs/MWh)': 'mcp'
}

def clean_excel_file(file_path):
    """
    Cleans the downloaded Excel file and returns a cleaned DataFrame.
    """
    try:
        
        # Read the Excel file
        df = pd.read_excel(file_path)

        # Cleaning operations
        df = df.drop(index=[0, 1, 2])  # Drop first 3 rows
        df = df.reset_index(drop=True)  # Reset index
        df.columns = df.iloc[0]  # Set first row as column names
        df = df.drop(0)  # Remove the header row
        df = df.reset_index(drop=True)  # Reset index again
        df = df[:-5]  # Remove the last 5 rows

        # Map the columns to match your Django model
        df = df.rename(columns=COLUMN_MAPPING)

        # Extract year, month, and day from the date column
        df['date'] = pd.to_datetime(df['date'], format='%d-%m-%Y', errors='coerce')
        df['year'] = df['date'].dt.year
        df['month'] = df['date'].dt.month
        df['day'] = df['date'].dt.day


        # Save cleaned data as a new Excel file
        cleaned_file = file_path.replace('.xlsx', '_cleaned.xlsx')
        df.to_excel(cleaned_file, index=False)

        return cleaned_file, df

    except Exception as e:
        logging.error(f"Error while cleaning Excel file: {str(e)}")
        return None, None


def save_to_model(df):
    """
    Saves the cleaned data into the CleanData model only if the record does not exist.
    """
    try:
        logging.info(df)
        df = df.where(pd.notnull(df), None)
        logging.info('================')
        logging.info(df)

        records = []
        existing_records = set(
            CleanData.objects.values_list(
                'date', 'hour', 'purchase_bid', 'total_sell_bid', 
                'sell_bid_solar', 'sell_bid_non_solar', 'sell_bid_hydro',
                'mcv_total', 'mcv_solar', 'mcv_non_solar', 'mcv_hydro', 'mcp'
            )
        )

        for _, row in df.iterrows():
            record_tuple = (
                row['date'], row['hour'], row['purchase_bid'], row['total_sell_bid'],
                row['sell_bid_solar'], row['sell_bid_non_solar'], row['sell_bid_hydro'],
                row['mcv_total'], row['mcv_solar'], row['mcv_non_solar'],
                row['mcv_hydro'], row['mcp']
            )

            if record_tuple not in existing_records:
                records.append(
                    CleanData(
                        date=row['date'],
                        hour=row['hour'],
                        purchase_bid=row['purchase_bid'],
                        total_sell_bid=row['total_sell_bid'],
                        sell_bid_solar=row['sell_bid_solar'],
                        sell_bid_non_solar=row['sell_bid_non_solar'],
                        sell_bid_hydro=row['sell_bid_hydro'],
                        mcv_total=row['mcv_total'],
                        mcv_solar=row['mcv_solar'],
                        mcv_non_solar=row['mcv_non_solar'],
                        mcv_hydro=row['mcv_hydro'],
                        mcp=row['mcp'],
                        year=row['year'],
                        month=row['month'],
                        day=row['day']
                    )
                )

        # Bulk insert only if there are new records
        if records:
            CleanData.objects.bulk_create(records)
            logging.info(f"✅ {len(records)} new records saved to model.")
            return f"{len(records)} new records saved successfully!"
        else:
            logging.info("✅ No new records to save.")
            return "No new records found."

    except IntegrityError as e:
        logging.error(f"❌ Integrity error: {str(e)}")
        return "Integrity error occurred."

    except Exception as e:
        tb = traceback.format_exc() 
        traceback_logger.error(f"Exception: {str(e)}\nTraceback:\n{tb}")  # Log error with traceback
        logging.error(f"❌ Failed to save data: {str(e)}")
        return "Failed to save data."

@shared_task
def scrape_iex_data():
    logging.debug("Scheduled task ran at %s", timezone.now())
    logger.debug("Scheduled task ran at %s", timezone.now())
    start_time = timezone.now()
    try:
        # Run the scraping script
        scrape_data()
        # Locate the latest Excel file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Define the path to the models folder
        download_folder = os.path.join(current_dir, "IEX_Data")

        # Find the latest file
        excel_files = [f for f in os.listdir(download_folder) if f.endswith('.xlsx') and '_cleaned' not in f]
        
        if not excel_files:
            logging.error("No Excel file found.")
            return "No Excel file found."

        # latest_file = max(excel_files, key=lambda f: os.path.getmtime(os.path.join(download_folder, f)))
        latest_file = f"IEX_Green_DAM_{timezone.now().strftime('%Y-%m-%d')}.xlsx"
        file_path = os.path.join(download_folder, latest_file)

        # Step 2: Clean the file
        cleaned_file, df = clean_excel_file(file_path)


        if cleaned_file and df is not None:
            # Step 3: Save cleaned data to the model
            save_to_model(df)
        else:
            logging.info("Cleaning failed.")
        
        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()

        # Log success message
        logging.info(f"Scrapping Task ran successfully in {duration:.2f} seconds.")
        return "Scraped IEX data successfully"

    except Exception as e:
        # Log any errors
        logging.error(f"Scrapping Task failed with error: {str(e)}")
        return f"Scrapping Task failed: {str(e)}"
    
@shared_task
def scrape_current_iex_data():
    logging.debug("Scheduled task ran at %s", timezone.now())
    logger.debug("Scheduled task ran at %s", timezone.now())
    start_time = timezone.now()
    try:
        # Run the scraping script
        scrape_current_data()
        # Locate the latest Excel file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Define the path to the models folder
        download_folder = os.path.join(current_dir, "IEX_Data")

        # Find the latest file
        excel_files = [f for f in os.listdir(download_folder) if f.endswith('.xlsx') and '_cleaned' not in f]
        
        if not excel_files:
            logging.error("No Excel file found.")
            return "No Excel file found."

        # latest_file = max(excel_files, key=lambda f: os.path.getmtime(os.path.join(download_folder, f)))
        latest_file = f"IEX_Green_DAM_{timezone.now().strftime('%Y-%m-%d')}.xlsx"
        file_path = os.path.join(download_folder, latest_file)

        # Step 2: Clean the file
        cleaned_file, df = clean_excel_file(file_path)


        if cleaned_file and df is not None:
            # Step 3: Save cleaned data to the model
            save_to_model(df)
        else:
            logging.info("Cleaning failed.")
        
        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()

        # Log success message
        logging.info(f"Scrapping Task ran successfully in {duration:.2f} seconds.")
        return "Scraped IEX data successfully"

    except Exception as e:
        # Log any errors
        logging.error(f"Scrapping Task failed with error: {str(e)}")
        return f"Scrapping Task failed: {str(e)}"