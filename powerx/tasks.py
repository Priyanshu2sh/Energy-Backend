import csv
import os
import re
import shutil
from accounts.models import User
from celery import shared_task
from powerx.AI_Model.model_scheduling import run_models_sequentially
from powerx.kaggle_runner import run_notebook, upload_dataset, upload_notebook
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
def model_training():
    # Predefined 96 time slots (24 hrs × 4 quarters)
    TIME_SLOTS = [
        "00:00 - 00:15", "00:15 - 00:30", "00:30 - 00:45", "00:45 - 01:00",
        "01:00 - 01:15", "01:15 - 01:30", "01:30 - 01:45", "01:45 - 02:00",
        "02:00 - 02:15", "02:15 - 02:30", "02:30 - 02:45", "02:45 - 03:00",
        "03:00 - 03:15", "03:15 - 03:30", "03:30 - 03:45", "03:45 - 04:00",
        "04:00 - 04:15", "04:15 - 04:30", "04:30 - 04:45", "04:45 - 05:00",
        "05:00 - 05:15", "05:15 - 05:30", "05:30 - 05:45", "05:45 - 06:00",
        "06:00 - 06:15", "06:15 - 06:30", "06:30 - 06:45", "06:45 - 07:00",
        "07:00 - 07:15", "07:15 - 07:30", "07:30 - 07:45", "07:45 - 08:00",
        "08:00 - 08:15", "08:15 - 08:30", "08:30 - 08:45", "08:45 - 09:00",
        "09:00 - 09:15", "09:15 - 09:30", "09:30 - 09:45", "09:45 - 10:00",
        "10:00 - 10:15", "10:15 - 10:30", "10:30 - 10:45", "10:45 - 11:00",
        "11:00 - 11:15", "11:15 - 11:30", "11:30 - 11:45", "11:45 - 12:00",
        "12:00 - 12:15", "12:15 - 12:30", "12:30 - 12:45", "12:45 - 13:00",
        "13:00 - 13:15", "13:15 - 13:30", "13:30 - 13:45", "13:45 - 14:00",
        "14:00 - 14:15", "14:15 - 14:30", "14:30 - 14:45", "14:45 - 15:00",
        "15:00 - 15:15", "15:15 - 15:30", "15:30 - 15:45", "15:45 - 16:00",
        "16:00 - 16:15", "16:15 - 16:30", "16:30 - 16:45", "16:45 - 17:00",
        "17:00 - 17:15", "17:15 - 17:30", "17:30 - 17:45", "17:45 - 18:00",
        "18:00 - 18:15", "18:15 - 18:30", "18:30 - 18:45", "18:45 - 19:00",
        "19:00 - 19:15", "19:15 - 19:30", "19:30 - 19:45", "19:45 - 20:00",
        "20:00 - 20:15", "20:15 - 20:30", "20:30 - 20:45", "20:45 - 21:00",
        "21:00 - 21:15", "21:15 - 21:30", "21:30 - 21:45", "21:45 - 22:00",
        "22:00 - 22:15", "22:15 - 22:30", "22:30 - 22:45", "22:45 - 23:00",
        "23:00 - 23:15", "23:15 - 23:30", "23:30 - 23:45", "23:45 - 24:00",
    ]

    try:
        # File name with today's date
        today_str = datetime.now().strftime("%Y-%m-%d")
        file_name = f"{today_str}_input_data.csv"

        # Path to save file on server
        current_dir = os.path.dirname(os.path.abspath(__file__))
        input_data_dir = os.path.join(current_dir, "input_data")
        os.makedirs(input_data_dir, exist_ok=True)
        file_path = os.path.join(input_data_dir, file_name)

        # Write CSV to disk
        with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)

            # Header
            writer.writerow([
                "Date",
                "Hour",
                "Time_x",
                "Purchase Bid (MW)",
                "Total Sell Bid (MW)",
                "Sell bid Solar (MW)",
                "Sell bid Non-Solar (MW)",
                "Sell bid Hydro (MW)",
                "MCV Total (MW)",
                "MCV Solar (MW)",
                "MCV Non-Solar (MW)",
                "MCV Hydro (MW)",
                "MCP (Rs/MWh)"
            ])

            queryset = CleanData.objects.all().order_by("date", "hour", "id")
            index = 0
            for obj in queryset:
                time_x = TIME_SLOTS[index % 96]
                index += 1

                writer.writerow([
                    obj.date.strftime("%Y-%m-%d"),
                    obj.hour,
                    time_x,
                    obj.purchase_bid,
                    obj.total_sell_bid,
                    obj.sell_bid_solar,
                    obj.sell_bid_non_solar,
                    obj.sell_bid_hydro,
                    obj.mcv_total,
                    obj.mcv_solar,
                    obj.mcv_non_solar,
                    obj.mcv_hydro,
                    obj.mcp,
                ])

        logging.info("file generated successfully")

        # model training using kaggle api
        upload_dataset()
        upload_notebook()
        run_notebook()

        src_folder = os.path.join(settings.BASE_DIR, "outputs")  # <-- change to your source folder
        dest_folder = os.path.join(settings.BASE_DIR, "powerx", "AI_Model", "models")

        if not os.path.exists(dest_folder):
            os.makedirs(dest_folder)

        # Regex to match filenames like 2025-09-26_next_day_mcp_model.pkl
        pattern = re.compile(r"(\d{4}-\d{2}-\d{2})_(next_day_mcp_model|next_day_mcv|scaler)\.pkl$")

        # Collect all files with valid pattern
        dated_files = {}
        for filename in os.listdir(src_folder):
            match = pattern.match(filename)
            if match:
                file_date_str = match.group(1)
                try:
                    file_date = datetime.strptime(file_date_str, "%Y-%m-%d").date()
                    dated_files.setdefault(file_date, []).append(filename)
                except ValueError:
                    continue

        if not dated_files:
            print("⚠️ No valid model files found in source folder.")
            return

        # Find latest date
        latest_date = max(dated_files.keys())
        latest_files = dated_files[latest_date]

        print(f"📌 Latest date detected: {latest_date}")
        print(f"📂 Files to copy: {latest_files}")

        # Copy each file to destination
        for filename in latest_files:
            src_path = os.path.join(src_folder, filename)
            dest_path = os.path.join(dest_folder, filename)
            shutil.copy2(src_path, dest_path)
            print(f"✅ Copied {filename}")

        print("🎯 Latest AI Model files copied successfully!")
        
    except Exception as e:
        tb = traceback.format_exc()  # Get the full traceback
        traceback_logger.error(f"Exception: {str(e)}\nTraceback:\n{tb}")  # Log error with traceback
        return f"Model Training Task failed: {str(e)}"