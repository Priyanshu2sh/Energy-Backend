import logging
from pymongo import MongoClient
import pandas as pd
import numpy as np
import os
from sklearn.preprocessing import MinMaxScaler
import joblib  
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from concurrent.futures import ThreadPoolExecutor
from django.conf import settings
from powerx.models import NextDayPrediction, CleanData

# MONGO_URI = "mongodb+srv://aartilahane2002:UIuuM11lxCg6lOsr@cluster0.e2suo.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
# DB_NAME = "iex_Data"
# CLEANED_COLLECTION = "iex_clean_data"

#change collection name
# PREDICTIONS_COLLECTION_MCP = "next_day_mcp_predictions"
# PREDICTIONS_COLLECTION_MCV = "next_day_mcv_predictions"

# client = MongoClient(MONGO_URI)
# db = client[DB_NAME]
# cleaned_collection = db[CLEANED_COLLECTION]
# predictions_collection_mcp = db[PREDICTIONS_COLLECTION_MCP]
# predictions_collection_mcv = db[PREDICTIONS_COLLECTION_MCV]


# Get the directory where the script is located
current_dir = os.path.dirname(os.path.abspath(__file__))

# Define the path to the models folder
models_folder = os.path.join(current_dir, "models")

model_path_mcp = os.path.join(models_folder, "next_day_mcp_model.pkl")
model_path_mcv = os.path.join(models_folder, "next_day_mcv.pkl")
scaler_path = os.path.join(models_folder, "scaler.pkl")

best_model_mcp = joblib.load(model_path_mcp)
best_model_mcv = joblib.load(model_path_mcv)
scaler = joblib.load(scaler_path)

scaler = MinMaxScaler()


# fetch 1 month data 96*30
def fetch_latest_96_blocks():
    data = list(CleanData.objects.all().values())  # Fetch all records
    # data = list(cleaned_collection.find())
    df = pd.DataFrame(data)
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
    if 'hour' in df.columns:
        df['hour'] = pd.to_numeric(df['hour'], errors='coerce')

    max_date = df['date'].max()
    latest_data = df[df['date'] == max_date]
    
    latest_data = latest_data.sort_values(by="hour", ascending=True)

    return latest_data

# firstly aggreagte hourly one month data
# preprocess and create lags based on colab file
def preprocess_data(latest_data):
    if 'date' in latest_data.columns:
        latest_data['date'] = pd.to_datetime(latest_data['date'])
    else:
        raise ValueError("The 'Date' column is missing from the DataFrame.")
    
    latest_data['prediction Date'] = latest_data['date'] + pd.Timedelta(days=2)
    columns_to_drop = ['Year', 'Month', 'Day', 'Time_x']
    latest_data = latest_data.drop(columns=[col for col in columns_to_drop if col in latest_data.columns], errors='ignore')

    latest_data['Year'] = latest_data['prediction Date'].dt.year
    latest_data['Month'] = latest_data['prediction Date'].dt.month
    latest_data['Day'] = latest_data['prediction Date'].dt.day
    latest_data['Day_Category'] = latest_data['prediction Date'].dt.weekday

    cols = ['Day_Category', 'Year', 'Month', 'Day', 'hour'] + [
        col for col in latest_data.columns if col not in ['Day_Category', 'Year', 'Month', 'Day', 'hour']
    ]
    latest_data = latest_data[cols]
    latest_data = latest_data.set_index('prediction Date')
    
    # Calculate Avg_Week_Hourly_MCP and Avg_Week_Hourly_MCV
    latest_data['Avg_Week_Hourly_MCP'] = (
        latest_data.groupby('hour')['mcp']
        .apply(lambda x: x.shift().rolling(window=672, min_periods=1).mean())
        .reset_index(level=0, drop=True)
    )
    latest_data['Avg_Week_Hourly_MCV'] = (
        latest_data.groupby('hour')['mcv_total']
        .apply(lambda x: x.shift().rolling(window=672, min_periods=1).mean())
        .reset_index(level=0, drop=True)
    )
    
    latest_data['Avg_Week_Hourly_MCP'].fillna(latest_data['mcp'].expanding().mean(), inplace=True)
    latest_data['Avg_Week_Hourly_MCV'].fillna(latest_data['mcv_total'].expanding().mean(), inplace=True)

    return latest_data


#feature selection based on colab
# def feature_selection_and_scaling_mcp(latest_data):
#     print("Before feature selection (MCP):")
#     print("Columns before feature selection:", latest_data.columns.tolist())
#     print("Shape:", latest_data.shape)

#     columns_to_keep = [col for col in latest_data if col not in [
#         'Sell bid Solar (MW)', 'Sell bid Non-Solar (MW)', 'Sell bid Hydro (MW)',
#         'MCV Solar (MW)', 'MCV Non-Solar (MW)', 'MCV Hydro (MW)', '_id', 'Date', 'Time_x'
#     ]]
    
#     df_selected = latest_data[columns_to_keep]
#     print("After feature selection (MCP):")
#     print("Columns after feature selection:", df_selected.columns.tolist())
#     print("Shape:", df_selected.shape)
    
#     input_data = df_selected
#     return input_data

def feature_selection_and_scaling(latest_data, target):
    print("Before feature selection (MCV):")
    print("Columns before feature selection:=====", latest_data.columns.tolist())
    print("Shape:", latest_data.shape)

    if target == 'MCV':
        columns_to_keep = [col for col in latest_data if col not in [
            'Sell bid Non-Solar (MW)', 'Sell bid Hydro (MW)',
            'MCV Solar (MW)', 'MCV Non-Solar (MW)', 'MCV Hydro (MW)', '_id', 'Date', 'Time_x'
        ]]
    elif target == 'MCP':
        columns_to_keep = [col for col in latest_data if col not in [
            'Sell bid Solar (MW)', 'Sell bid Non-Solar (MW)', 'Sell bid Hydro (MW)',
            'MCV Solar (MW)', 'MCV Non-Solar (MW)', 'MCV Hydro (MW)', '_id', 'Date', 'Time_x'
        ]]
    
    df_selected = latest_data[columns_to_keep]
    print("After feature selection (MCV):")
    print("Columns after feature selection:", df_selected.columns.tolist())
    print("Shape:", df_selected.shape)
    
    input_data = df_selected
    return input_data


#for prediction use used month ahead model
def make_predictions_mcp(input_data):
    if input_data is None or len(input_data) == 0:
        raise ValueError("No data available for MCP predictions.")
    column_mapping = {
        "hour": "Hour",
        "purchase_bid": "Purchase Bid (MW)",
        "total_sell_bid": "Total Sell Bid (MW)",
        "mcv_total": "MCV Total (MW)",
        "mcp": "MCP (Rs/MWh)"
    }

    input_data = input_data.rename(columns=column_mapping)
    # Define the expected feature names
    expected_features = ['Day_Category', 'Year', 'Month', 'Day', 'Hour', 'Purchase Bid (MW)', 'Total Sell Bid (MW)', 'MCV Total (MW)', 'MCP (Rs/MWh)', 'Avg_Week_Hourly_MCP', 'Avg_Week_Hourly_MCV']
    print('---------')
    print(input_data.columns.tolist())
    print('---------')

    # Keep only the expected columns and remove others
    input_data = input_data[expected_features]

    print("Columns in input data:", input_data.columns.tolist())
    print("Expected feature names:", best_model_mcp.feature_names_in_.tolist())
    predictions = best_model_mcp.predict(input_data)
    print('')
    return predictions

def make_predictions_mcv(input_data):
    if input_data is None or len(input_data) == 0:
        raise ValueError("No data available for MCV predictions.")
    column_mapping = {
        "hour": "Hour",
        "purchase_bid": "Purchase Bid (MW)",
        "total_sell_bid": "Total Sell Bid (MW)",
        "mcv_total": "MCV Total (MW)",
        "mcp": "MCP (Rs/MWh)",
        "sell_bid_solar": "Sell bid Solar (MW)",
        "sell_bid_non_solar": "Sell bid Non-Solar (MW)",
        "sell_bid_hydro": "Sell bid Hydro (MW)",
        "mcv_solar": "MCV Solar (MW)",
        "mcv_non_solar": "MCV Non-Solar (MW)",
        "mcv_hydro": "MCV Hydro (MW)",
    }

    input_data = input_data.rename(columns=column_mapping)
    # Define the expected feature names
    expected_features = ['Day_Category', 'Year', 'Month', 'Day', 'Hour', 'Purchase Bid (MW)', 'Total Sell Bid (MW)', 'Sell bid Solar (MW)','Sell bid Non-Solar (MW)', 'Sell bid Hydro (MW)', 'MCV Total (MW)', 'MCV Solar (MW)', 'MCV Non-Solar (MW)', 'MCV Hydro (MW)', 'MCP (Rs/MWh)', 'Avg_Week_Hourly_MCP', 'Avg_Week_Hourly_MCV']
    print('---------')
    print(input_data.columns.tolist())
    print('---------')

    # Keep only the expected columns and remove others
    input_data = input_data[expected_features]

    print("Columns in input data:", input_data.columns.tolist())
    print("Expected feature names:", best_model_mcv.feature_names_in_.tolist())
    predictions = best_model_mcv.predict(input_data)
    print('pppppp', predictions)
    return predictions

# def save_prediction_mcp(predictions, preprocess_data):
#     records = []
#     prediction_dates = preprocess_data.index
#     # time_x_values = preprocess_data['Time_x'].values
#     hour_values = preprocess_data['hour'].values
#     print(preprocess_data.columns.tolist())

#     for i, prediction in enumerate(predictions):
#         record = {
#             "Date": prediction_dates[i].strftime("%Y-%m-%d"),
#             "hour": hour_values[i], 
#             "Prediction": prediction
#         }
#         records.append(record)
#     sorted_records = sorted(records, key=lambda x: (x['Date'], x['hour']))

#     # Mapping dictionary to rename columns to match model fields
#     column_mapping = {
#         'Date': 'date',
#         'hour': 'hour',
#         'Prediction': 'mcp_prediction',  # Assuming 'Prediction' refers to MCP
#         'MCV_Prediction': 'mcv_prediction'  # Assuming this is MCV
#     }

#     # Rename keys in each dictionary
#     formatted_records = [
#         {column_mapping.get(k, k): v for k, v in record.items()} for record in sorted_records
#     ]

#     # Get existing records that match date & hour
#     existing_records = {
#         (record.date, record.hour): record for record in NextDayPrediction.objects.filter(
#             date__in=[r['date'] for r in formatted_records],
#             hour__in=[r['hour'] for r in formatted_records]
#         )
#     }

#     new_objects = []
#     update_objects = []

#     for record in formatted_records:
#         key = (record['date'], record['hour'])
#         if key in existing_records:
#             # Update existing record
#             existing_record = existing_records[key]
#             existing_record.mcv_prediction = record['mcv_prediction']
#             existing_record.mcp_prediction = record['mcp_prediction']
#             update_objects.append(existing_record)
#         else:
#             # Create new record
#             new_objects.append(NextDayPrediction(**record))

#     # Bulk update existing records
#     if update_objects:
#         NextDayPrediction.objects.bulk_update(update_objects, ['mcv_prediction', 'mcp_prediction'])

#     # Bulk create new records
#     if new_objects:
#         NextDayPrediction.objects.bulk_create(new_objects)
#     print(f"Saved {len(sorted_records)} MCP predictions to the database.")

def save_prediction(predictions, preprocess_data, target):
    records = []
    prediction_dates = preprocess_data.index
    print(preprocess_data.columns.tolist())
    hour_values = preprocess_data['hour'].values
    logging.info(f'dates--------  {prediction_dates}')

    if target == 'MCV':
        for i, prediction in enumerate(predictions):
            record = {
                "date": prediction_dates[i].strftime("%Y-%m-%d"),
                "hour": hour_values[i], 
                "mcv_prediction": prediction
            }
            records.append(record)
    elif target == 'MCP':
        for i, prediction in enumerate(predictions):
            record = {
                "date": prediction_dates[i].strftime("%Y-%m-%d"),
                "hour": hour_values[i], 
                "mcp_prediction": prediction
            }
            records.append(record)

    sorted_records = sorted(records, key=lambda x: (x['date'], x['hour']))
    if sorted_records:
        objects_to_create = []
        objects_to_update = []
        for record in sorted_records:
            # Check if a record already exists for the same date and hour
            existing_record = NextDayPrediction.objects.filter(
                date=record["date"], hour=record["hour"]
            ).first()
            if existing_record:
                # Update existing record
                if target == "MCV":
                    existing_record.mcv_prediction = record["mcv_prediction"]
                elif target == "MCP":
                    existing_record.mcp_prediction = record["mcp_prediction"]
                objects_to_update.append(existing_record)
            else:
                # Create new record
                objects_to_create.append(NextDayPrediction(**record))
        # Bulk update and create records
        if objects_to_update:
            NextDayPrediction.objects.bulk_update(objects_to_update, ["mcv_prediction", "mcp_prediction"])
        if objects_to_create:
            NextDayPrediction.objects.bulk_create(objects_to_create)
        print(f"Saved {len(sorted_records)} {target} predictions to the database.")
    else:
        print(f"No records to insert for {target}.")

def run_predictions():
    max_date = fetch_latest_96_blocks()
    preprocess = preprocess_data(max_date)

    input_data_mcv = feature_selection_and_scaling(preprocess, 'MCV')
    predictions_mcv = make_predictions_mcv(input_data_mcv)
    print('++++++++', len(predictions_mcv))
    save_prediction(predictions_mcv, preprocess, 'MCV')

    input_data_mcp = feature_selection_and_scaling(preprocess , 'MCP')
    predictions_mcp = make_predictions_mcp(input_data_mcp)
    print('++++++++', len(predictions_mcp))
    save_prediction(predictions_mcp, preprocess, 'MCP')


if __name__ == "__main__":
    try:
        with ThreadPoolExecutor() as executor:
            executor.submit(run_predictions)
    except Exception as e:
        print("Error during prediction:", str(e))
