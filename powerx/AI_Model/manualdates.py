from http.client import HTTPException
from django.conf import settings
import requests
import pandas as pd
import os
from datetime import datetime, timedelta
from pymongo import MongoClient
from rest_framework.exceptions import APIException
from powerx.models import CleanData

MONGO_URI ="mongodb+srv://aartilahane2002:ARwggdMgphRRaGe7@cluster0.e2suo.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "iex_Data"  
COLLECTION_NAME = "iex_clean_data" 
 
def fetch_data_from_api(date):
    # api_url = f"http://127.0.0.1:8000/data/{date}"
    # response = requests.get(api_url)

    # if response.status_code == 200:
    #     return pd.DataFrame(response.json())
    # else:
    #     raise Exception(f"Failed to fetch data: {response.json().get('detail')}")
    if isinstance(date, datetime):  # If date is a datetime object, convert it to a string
        date = date.strftime("%Y-%m-%d")
    
    current_dir = os.path.dirname(os.path.abspath(__file__))  # Get the directory of the current script
    file_path = os.path.join(current_dir, "market_data_nov2022_to_jan2025.xlsx")  # Construct file path


    dummy_data = pd.read_excel(file_path)

    dummy_data['Date'] = pd.to_datetime(dummy_data['Date']).dt.date
    try:
        query_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise APIException("Invalid date format. Use YYYY-MM-DD.")

    filtered_data = dummy_data[dummy_data['Date'] == query_date]

    if filtered_data.empty:
        raise APIException("No data found for the given date.")  

    # return filtered_data.to_dict(orient="records")
    return filtered_data

def clean_and_process_data(data: pd.DataFrame):
    print("Initial Data:")
    print(data.head())
    
    if data.empty:
        print("No data to process!")
        return pd.DataFrame()

    data.rename(columns={'MCP (Rs/MWh) ': 'MCP (Rs/MWh)'}, inplace=True)

    data['Date'] = pd.to_datetime(data['Date'])

    data['Year'] = data['Date'].dt.year
    data['Month'] = data['Date'].dt.month
    data['Day'] = data['Date'].dt.day

    data.set_index('Date', inplace=True)
    data.sort_values(by='Hour', ascending=True, inplace=True)

    print("Data after processing and sorting:")
    print(data.head())

    return data

def main():
    date_input = input("Enter the date for fetching data (YYYY-MM-DD): ")

    if not date_input:
        current_date = datetime.now().date()
        date_input = (current_date - timedelta(days=1)).strftime("%Y-%m-%d")  # Default to yesterday
    
    try:
        raw_data = fetch_data_from_api(date_input)
        print(f"Fetched data for {date_input} successfully.")
        
        cleaned_data = clean_and_process_data(raw_data)
        print("Data cleaned, processed, and sorted.")

        file_path = os.path.join("files", f"cleaned_data_{date_input}.xlsx")
        cleaned_data.to_excel(file_path, index=True)

        try:
            client = MongoClient(MONGO_URI)
            db = client[DB_NAME]
            print("Connected to MongoDB!")
        except Exception as e:
            print('error- ', e)
        collection = db[COLLECTION_NAME]
        cleaned_data_dict = cleaned_data.reset_index().to_dict(orient="records")

        collection.insert_many(cleaned_data_dict)
        print(f"Inserted data into MongoDB collection '{COLLECTION_NAME}' in database '{DB_NAME}'.")

    except Exception as e:
        print(f"Error occurred: {e}")


def process_and_store_data(date_input: str):
    try:
        raw_data = fetch_data_from_api(date_input)
        print(type(raw_data))
        cleaned_data = clean_and_process_data(raw_data)

        current_dir = os.path.dirname(os.path.abspath(__file__)) 
        file_path = os.path.join(current_dir, "files", f"cleaned_data_{date_input}.xlsx")
        cleaned_data.to_excel(file_path, index=True)

        cleaned_data_dict = cleaned_data.reset_index().to_dict(orient="records")

        FIELD_MAPPING = {
            "Date": "date",
            "Hour": "hour",
            "Purchase Bid (MW)": "purchase_bid",
            "Total Sell Bid (MW)": "total_sell_bid",
            "Sell bid Solar (MW)": "sell_bid_solar",
            "Sell bid Non-Solar (MW)": "sell_bid_non_solar",
            "Sell bid Hydro (MW)": "sell_bid_hydro",
            "MCV Total (MW)": "mcv_total",
            "MCV Solar (MW)": "mcv_solar",
            "MCV Non-Solar (MW)": "mcv_non_solar",
            "MCV Hydro (MW)": "mcv_hydro",
            "MCP (Rs/MWh)": "mcp",
            "Year": "year",
            "Month": "month",
            "Day": "day",
        }

        instances = []

        for data in cleaned_data_dict:
            if isinstance(data, dict):  # Ensure data is a dictionary
                mapped_data = {FIELD_MAPPING[key]: value for key, value in data.items() if key in FIELD_MAPPING and key != "Time_x"}
                instances.append(CleanData(**mapped_data))
            else:
                print(f"Skipping non-dictionary entry: {data}, {type(data)}")  # Debugging info

        # Bulk insert if there are valid instances
        if instances:
            CleanData.objects.bulk_create(instances)

        return {"message": f"Data for {date_input} processed and stored successfully.", "data": cleaned_data_dict}
    except Exception as e:
        return {"error": str(e)}
    

# Run the script
# if __name__ == "__main__":
#     main()


# Keep CLI execution for testing
if __name__ == "__main__":
    date_input = input("Enter the date for fetching data (YYYY-MM-DD): ")
    if not date_input:
        date_input = (datetime.now().date() - timedelta(days=1)).strftime("%Y-%m-%d")  # Default to yesterday
    result = process_and_store_data(date_input)
    print(result)