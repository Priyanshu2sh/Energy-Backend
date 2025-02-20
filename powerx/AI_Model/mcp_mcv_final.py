from pymongo import MongoClient
import pandas as pd
import numpy as np
import os
from sklearn.preprocessing import MinMaxScaler
import joblib  
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from concurrent.futures import ThreadPoolExecutor

MONGO_URI = "mongodb+srv://aartilahane2002:UIuuM11lxCg6lOsr@cluster0.e2suo.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "iex_Data"
CLEANED_COLLECTION = "iex_clean_data"

#change collection name
PREDICTIONS_COLLECTION_MCP = "next_day_mcp_predictions"
PREDICTIONS_COLLECTION_MCV = "next_day_mcv_predictions"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
cleaned_collection = db[CLEANED_COLLECTION]
predictions_collection_mcp = db[PREDICTIONS_COLLECTION_MCP]
predictions_collection_mcv = db[PREDICTIONS_COLLECTION_MCV]


#create models folder and save models n that folder
models_folder = "models"

model_path_mcp = os.path.join(models_folder, "next_day_mcp_model.pkl")
model_path_mcv = os.path.join(models_folder, "next_day_mcv.pkl")
scaler_path = os.path.join(models_folder, "scaler.pkl")

best_model_mcp = joblib.load(model_path_mcp)
best_model_mcv = joblib.load(model_path_mcv)
scaler = joblib.load(scaler_path)

scaler = MinMaxScaler()


# fetch 1 month data 96*30
def fetch_latest_96_blocks():
    data = list(cleaned_collection.find())
    df = pd.DataFrame(data)
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
    if 'Hour' in df.columns:
        df['Hour'] = pd.to_numeric(df['Hour'], errors='coerce')

    max_date = df['Date'].max()
    latest_data = df[df['Date'] == max_date]
    
    latest_data = latest_data.sort_values(by="Hour", ascending=True)

    return latest_data

# firstly aggreagte hourly one month data
# preprocess and create lags based on colab file
def preprocess_data(latest_data):
    if 'Date' in latest_data.columns:
        latest_data['Date'] = pd.to_datetime(latest_data['Date'])
    else:
        raise ValueError("The 'Date' column is missing from the DataFrame.")
    
    if 'Time_x' in latest_data.columns:
        time_x_column = latest_data['Time_x']
    else:
        raise ValueError("The 'Time_x' column is missing from the DataFrame.")

    latest_data['prediction Date'] = latest_data['Date'] + pd.Timedelta(days=2)
    columns_to_drop = ['Year', 'Month', 'Day', 'Time_x']
    latest_data = latest_data.drop(columns=[col for col in columns_to_drop if col in latest_data.columns], errors='ignore')

    latest_data['Year'] = latest_data['prediction Date'].dt.year
    latest_data['Month'] = latest_data['prediction Date'].dt.month
    latest_data['Day'] = latest_data['prediction Date'].dt.day
    latest_data['Day_Category'] = latest_data['prediction Date'].dt.weekday

    cols = ['Day_Category', 'Year', 'Month', 'Day', 'Hour'] + [
        col for col in latest_data.columns if col not in ['Day_Category', 'Year', 'Month', 'Day', 'Hour']
    ]
    latest_data = latest_data[cols]
    latest_data = latest_data.set_index('prediction Date')
    
    # Calculate Avg_Week_Hourly_MCP and Avg_Week_Hourly_MCV
    latest_data['Avg_Week_Hourly_MCP'] = (
        latest_data.groupby('Hour')['MCP (Rs/MWh)']
        .apply(lambda x: x.shift().rolling(window=672, min_periods=1).mean())
        .reset_index(level=0, drop=True)
    )
    latest_data['Avg_Week_Hourly_MCV'] = (
        latest_data.groupby('Hour')['MCV Total (MW)']
        .apply(lambda x: x.shift().rolling(window=672, min_periods=1).mean())
        .reset_index(level=0, drop=True)
    )
    
    latest_data['Avg_Week_Hourly_MCP'].fillna(latest_data['MCP (Rs/MWh)'].expanding().mean(), inplace=True)
    latest_data['Avg_Week_Hourly_MCV'].fillna(latest_data['MCV Total (MW)'].expanding().mean(), inplace=True)

    latest_data['Time_x'] = time_x_column.values

    return latest_data


#feature selection based on colab
def feature_selection_and_scaling_mcp(latest_data):
    print("Before feature selection (MCP):")
    print("Columns before feature selection:", latest_data.columns.tolist())
    print("Shape:", latest_data.shape)

    columns_to_keep = [col for col in latest_data if col not in [
        'Sell bid Solar (MW)', 'Sell bid Non-Solar (MW)', 'Sell bid Hydro (MW)',
        'MCV Solar (MW)', 'MCV Non-Solar (MW)', 'MCV Hydro (MW)', '_id', 'Date', 'Time_x', 'Avg_Week_Hourly_MCV'
    ]]
    
    df_selected = latest_data[columns_to_keep]
    print("After feature selection (MCP):")
    print("Columns after feature selection:", df_selected.columns.tolist())
    print("Shape:", df_selected.shape)
    
    input_data = df_selected
    return input_data

def feature_selection_and_scaling_mcv(latest_data):
    print("Before feature selection (MCV):")
    print("Columns before feature selection:", latest_data.columns.tolist())
    print("Shape:", latest_data.shape)

    columns_to_keep = [col for col in latest_data if col not in [
        'Sell bid Solar (MW)', 'Sell bid Non-Solar (MW)', 'Sell bid Hydro (MW)',
        'MCV Solar (MW)', 'MCV Non-Solar (MW)', 'MCV Hydro (MW)', '_id', 'Date', 'Time_x', 'Avg_Week_Hourly_MCP'
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
    predictions = best_model_mcp.predict(input_data)
    return predictions

def make_predictions_mcv(input_data):
    if input_data is None or len(input_data) == 0:
        raise ValueError("No data available for MCV predictions.")
    predictions = best_model_mcv.predict(input_data)
    return predictions

def save_prediction_mcp(predictions, preprocess_data):
    records = []
    prediction_dates = preprocess_data.index
    time_x_values = preprocess_data['Time_x'].values

    for i, prediction in enumerate(predictions):
        record = {
            "Date": prediction_dates[i].strftime("%Y-%m-%d"),
            "Time_x": time_x_values[i], 
            "Prediction": prediction
        }
        records.append(record)
    sorted_records = sorted(records, key=lambda x: (x['Date'], x['Time_x']))
    
    predictions_collection_mcp.insert_many(sorted_records)
    print(f"Saved {len(sorted_records)} MCP predictions to the database.")

def save_prediction_mcv(predictions, preprocess_data):
    records = []
    prediction_dates = preprocess_data.index
    time_x_values = preprocess_data['Time_x'].values

    for i, prediction in enumerate(predictions):
        record = {
            "Date": prediction_dates[i].strftime("%Y-%m-%d"),
            "Time_x": time_x_values[i], 
            "Prediction": prediction
        }
        records.append(record)
    sorted_records = sorted(records, key=lambda x: (x['Date'], x['Time_x']))
    
    predictions_collection_mcv.insert_many(sorted_records)
    print(f"Saved {len(sorted_records)} MCV predictions to the database.")

def run_predictions():
    max_date = fetch_latest_96_blocks()
    preprocess = preprocess_data(max_date)

    input_data_mcp = feature_selection_and_scaling_mcp(preprocess)
    predictions_mcp = make_predictions_mcp(input_data_mcp)
    save_prediction_mcp(predictions_mcp, preprocess)

    input_data_mcv = feature_selection_and_scaling_mcv(preprocess)
    predictions_mcv = make_predictions_mcv(input_data_mcv)
    save_prediction_mcv(predictions_mcv, preprocess)

if __name__ == "__main__":
    try:
        with ThreadPoolExecutor() as executor:
            executor.submit(run_predictions)
    except Exception as e:
        print("Error during prediction:", str(e))
