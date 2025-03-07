from pymongo import MongoClient
import pandas as pd
import numpy as np
import os
from sklearn.preprocessing import MinMaxScaler
import joblib
from concurrent.futures import ThreadPoolExecutor
from powerx.models import CleanData, MonthAheadPrediction
from tensorflow.keras.models import load_model



# Get the directory where the script is located
current_dir = os.path.dirname(os.path.abspath(__file__))

# Define the path to the models folder
models_folder = os.path.join(current_dir, "models")

model_path_mcv = os.path.join(models_folder, "mcv_month_ahead1_lstm_model.h5")
best_model_mcv = load_model(model_path_mcv)

scaler_X_path = os.path.join(models_folder, "mcv_month_ahead_scaler_X.pkl")
scaler_Y_mcv_path = os.path.join(models_folder, "mcv_month_ahead_scaler_y.pkl")

scaler_X = joblib.load(scaler_X_path)
scaler_Y_mcv = joblib.load(scaler_Y_mcv_path)

def fetch_previous_2880_blocks():
    data = list(CleanData.objects.all().values())
    df = pd.DataFrame(data)

    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
    if 'hour' in df.columns:
        df['hour'] = pd.to_numeric(df['hour'], errors='coerce')

    max_date = df['date'].max()
    date_1_month_ago = max_date - pd.Timedelta(days=30)
    previous_2880_data = df[df['date'] > date_1_month_ago]
    previous_2880_data = previous_2880_data.sort_values(by=["date", "hour"], ascending=True)
    previous_2880_data = previous_2880_data.tail(2880)

    # Copy the data to avoid modifying the original DataFrame
    df = previous_2880_data.copy()

    df = df.sort_values(by=['date', 'hour'])

    # Create a new column to group every 4 rows
    df['group'] = df.index // 4

    # Group by 'group' and sum the values
    df_hourly = df.groupby('group').agg({
        'date': 'first',  # Keep the first date
        'hour': 'first',  # Keep the first hour
        'purchase_bid': 'sum',
        'total_sell_bid': 'sum',
        'sell_bid_solar': 'sum',
        # Add other columns you want to sum here
        'mcv_non_solar': 'sum',
        'mcv_hydro': 'sum',
        'mcp': 'mean',  # Use mean for mcp if it's not supposed to be summed
        'year': 'first',
        'month': 'first',
        'day': 'first'
    }).reset_index(drop=True)

    # Adjust the hour column to be sequential
    df_hourly['hour'] = df_hourly.index + 1

    return previous_2880_data

def preprocess_data(previous_2880_data):
    if 'date' not in previous_2880_data.columns:
        raise ValueError("The 'Date' column is missing from the DataFrame.")

    previous_2880_data['date'] = pd.to_datetime(previous_2880_data['date'])

    columns_to_drop = ['year', 'month', 'day']
    latest_data = previous_2880_data.drop(columns=[col for col in columns_to_drop if col in previous_2880_data.columns], errors='ignore')

    latest_data['year'] = latest_data['date'].dt.year
    latest_data['month'] = latest_data['date'].dt.month
    latest_data['day'] = latest_data['date'].dt.day
    latest_data['Day_Category'] = latest_data['date'].dt.weekday

    latest_data = latest_data.sort_values(by=['date', 'hour']).reset_index(drop=True)
    latest_data['MCP_lag_1'] = latest_data['mcp'].shift(24)
    latest_data['MCV_lag_1'] = latest_data['mcv_total'].shift(24)


    latest_data['MCP_avg'] = latest_data['mcp'].rolling(window=24).mean()  # Daily average for MCP
    latest_data['MCV_avg'] = latest_data['mcv_total'].rolling(window=24).mean()  # Daily average for MCV

    latest_data['MCP_7d_avg'] = latest_data['mcp'].rolling(window=24 * 7).mean()  # Weekly average for MCP
    latest_data['MCV_7d_avg'] = latest_data['mcv_total'].rolling(window=24 * 7).mean()  # Weekly average for MCV

    latest_data['monthly_avg_MCP'] = latest_data['mcp'].rolling(window=24 * 30).mean()  # Monthly average for MCP
    latest_data['monthly_avg_MCV'] = latest_data['mcv_total'].rolling(window=24 * 30).mean()  # Monthly average for MCV

    # Drop NaN values after adding new columns
    latest_data.dropna(inplace=True)

    cols = ['Day_Category', 'year', 'month', 'day', 'hour'] + [
        col for col in latest_data.columns if col not in ['Day_Category', 'year', 'month', 'day', 'hour']
    ]
    latest_data = latest_data[cols]
    latest_data = latest_data.set_index('date')

    print(latest_data)
    return latest_data

def feature_selection_and_scaling(latest_data, target):
    print(f"Before feature selection ({target}):")
    print("Columns before feature selection:", latest_data.columns.tolist())
    print("Shape:", latest_data.shape)

    columns_to_keep = [col for col in latest_data if col not in [
        'Datetime', 'mcp', 'MCP_lag_1', 'MCP_avg', 'MCP_7d_avg', 
    ]]

    df_selected = latest_data[columns_to_keep]
    print(f"After feature selection ({target}):")
    print("Columns after feature selection:", df_selected.columns.tolist())
    print("Selected shape:",    df_selected.shape)
    df_selected = df_selected.rename(columns={'mcv_total': 'MCV Total (MW)'})
    df_selected=df_selected[['MCV Total (MW)', 'MCV_lag_1', 'MCV_avg', 'MCV_7d_avg']]

    scaler = scaler_X
    print('-----------', df_selected.head())

    input_data = scaler.transform(df_selected)
    print("Scaled data shape:", input_data.shape)
    print("Scaled data sample (first 5 rows):\n", input_data[:5])
    # only take below columns in input_data---------------------------------
    # Datetime
    # MCP (Rs/MWh)
    # MCP_lag_1	
    # MCP_avg
    # MCP_7d_avg------------------------------------------------------------

    return input_data

# def make_predictions(input_data, model, sequence_length):
#     if input_data is None or len(input_data) == 0:
#         raise ValueError("No data available for predictions.")
#     num_features = input_data.shape[1]
#     # required_size = sequence_length * num_features
#     # input_data = input_data[:required_size]
#     print("Input data shape before reshaping:", input_data.shape)

#     reshaped_data = input_data.reshape(1, sequence_length, num_features)

#     predictions = model.predict(reshaped_data)
#     print("Prediction successful")
#     return predictions

def make_predictions(input_data, model, sequence_length):
    if input_data is None or len(input_data) == 0:
        raise ValueError("No data available for predictions.")
    
    num_samples, num_features = input_data.shape
    print(f"Input Data Shape: {input_data.shape} | Required: ({sequence_length}, {num_features})")

    # Ensure we have exactly `sequence_length` samples
    if num_samples > sequence_length:
        input_data = input_data[-sequence_length:]  # Take last `sequence_length` rows
    elif num_samples < sequence_length:
        padding_needed = sequence_length - num_samples
        padding = np.zeros((padding_needed, num_features))
        input_data = np.vstack((padding, input_data))  # Pad with zeros at the beginning

    print("Final input data shape after trimming/padding:", input_data.shape)

    # Reshape to (1, sequence_length, num_features)
    reshaped_data = input_data.reshape(1, sequence_length, num_features)
    
    # Predict
    predictions = model.predict(reshaped_data)
    print("Prediction successful")
    return predictions


def save_predictions(predictions, preprocess_data, scaler_Y, target):
    try:
        predictions_original = scaler_Y.inverse_transform(predictions.reshape(-1, 1))
        records = []
        prediction_dates = preprocess_data.index
        hour_values = preprocess_data['hour'].values

        if len(prediction_dates) != len(predictions_original):
            raise ValueError("Mismatch between prediction dates and predictions.")

        max_input_date = prediction_dates.max()
        shifted_start_date = max_input_date + pd.Timedelta(days=1)
        prediction_dates_shifted = []

        for i, prediction in enumerate(predictions_original):
            record = {
                "date": prediction_dates_shifted[i].strftime("%Y-%m-%d %H:%M"),
                "hour": hour_values[i],
                "mcv_prediction": float(prediction[0])
            }
            records.append(record)

        sorted_records = sorted(records, key=lambda x: (x['date'], x['hour']))
        print('-------------------', sorted_records)

        if sorted_records:
            # Convert dictionaries into model instances
            objects_to_create = [
                MonthAheadPrediction(**record) for record in sorted_records
            ]

            # predictions_collection_mcv.insert_many(sorted_records)
            MonthAheadPrediction.objects.bulk_create(objects_to_create)
            print(f"Saved {len(sorted_records)} MCV predictions to the database.")
        else:
            print(f"No records to insert for {target}.")
    except Exception as e:
        print(f"Error saving {target} predictions to MongoDB:", str(e))

# def run_mcp_predictions():
#     previous_data = fetch_previous_672_blocks()
#     preprocess = preprocess_data(previous_data)
#     input_data = feature_selection_and_scaling(preprocess, "MCP")
#     predictions = make_predictions(input_data, best_model_mcp, sequence_length=96 * 7)
#     save_predictions(predictions, preprocess, scaler_Y_mcp, "MCP", predictions_collection_mcp)

def run_mcv_predictions():
    previous_data = fetch_previous_2880_blocks()
    preprocess = preprocess_data(previous_data)
    input_data = feature_selection_and_scaling(preprocess, "MCV")
    predictions = make_predictions(input_data, best_model_mcv, sequence_length=24*30)
    save_predictions(predictions, preprocess, scaler_Y_mcv, "MCV") #this is the table where we will store the data - predictions_collection_mcv

if __name__ == "__main__":
    try:
        with ThreadPoolExecutor() as executor:
            # executor.submit(run_mcp_predictions)
            executor.submit(run_mcv_predictions)
    except Exception as e:
        print("Error during prediction:", str(e))