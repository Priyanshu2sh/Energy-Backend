import base64

# try:
#     with open("C:\\Users\\ps200\\Desktop\\Prushal Tech\\Energy Transition\\energy_transition\\energy\\12monthdatatemplate(updated).csv", "rb") as file:
#         encoded_bytes = base64.b64encode(file.read())
#         encoded_str = encoded_bytes.decode('utf-8')
#         print(encoded_str)
# except FileNotFoundError:
#     print("File not found. Please check the path.")
# except Exception as e:
#     print(f"Error: {str(e)}")


# import pandas as pd

# # Step 1: Read the text file
# with open("C:\\Users\\ps200\\Desktop\\Prushal Tech\\Energy Transition\\energy_transition\\energy\\consumer hourly demand.txt", "r") as file:
#     content = file.read()

# # Step 2: Split the comma-separated values into a list
# values = content.strip().split(',')

# # Step 3: Create a DataFrame with a single column
# df = pd.DataFrame(values, columns=["Demand"])

# # Step 4: Save it to an Excel file
# df.to_excel("hourly_demand_column.xlsx", index=False)

# print("Excel file 'hourly_demand_column.xlsx' created successfully.")



# import pandas as pd

# # Step 1: Read original Excel or TXT file column
# with open("C:\\Users\\ps200\\Desktop\\Prushal Tech\\Energy Transition\\energy_transition\\energy\\without_agg_demand.txt", "r") as file:
#     values = [float(line.strip()) for line in file if line.strip()]

# # Step 2: Create a DataFrame
# df = pd.DataFrame(values, columns=["Demand"])

# # Step 3: Group every 4 rows and sum
# grouped = df.groupby(df.index // 4).sum()

# # Step 4: Save to Excel
# grouped.to_excel("aggregated_demand.xlsx", index=False)

# print("✅ Aggregated Excel file 'aggregated_demand.xlsx' created.")



# from datetime import datetime, timedelta
# import pandas as pd

# # Step 1: Define date range
# start_date = datetime(2025, 1, 1)  # data starts from Jan 1, 2025
# from_date = datetime(2025, 3, 1)
# to_date = datetime(2025, 4, 1)  # include all 24 hours of Sept 1

# # Step 2: Calculate starting and ending line indices
# start_index = int((from_date - start_date).total_seconds() / 3600)
# end_index = int((to_date - start_date).total_seconds() / 3600)

# # Step 3: Read all lines and slice the desired range
# with open("C:\\Users\\ps200\\Desktop\\Prushal Tech\\Energy Transition\\energy_transition\\energy\\demand_in_column.txt", "r") as file:
#     lines = [float(line.strip()) for line in file if line.strip()]

# # Step 4: Extract the desired values
# selected_values = lines[start_index:end_index + 1]

# # Step 5: Save to Excel
# df = pd.DataFrame(selected_values, columns=["Hourly Demand"])
# df.to_excel("new.xlsx", index=False)

# print("✅ Extracted data saved to 'new.xlsx'")



# import pandas as pd

# # Load your Excel file
# df = pd.read_excel("C:\\Users\\ps200\\Desktop\\Prushal Tech\\Energy Transition\\energy_transition\\energy\\aggregated_demand.xlsx")  # Replace with your actual file path

# # Generate datetime index from 1st Sept 2024, hourly for the number of rows in your file
# start_time = pd.Timestamp("2024-09-01 00:00")
# df['Datetime'] = pd.date_range(start=start_time, periods=len(df), freq='h')

# # Extract hour from Datetime
# df['Hour'] = df['Datetime'].dt.hour

# # Define peak hours (morning: 7-10, evening: 18-21)
# peak_hours = [7, 8, 9, 10, 18, 19, 20, 21]

# # Filter rows where hour is in peak_hours
# peak_df = df[df['Hour'].isin(peak_hours)]

# # Optional: Keep only needed columns
# peak_df = peak_df[['Datetime', 'scada hourly MWh', 'hourly system MWh']]

# # Save to new Excel file
# peak_df.to_excel("peak_hours_output.xlsx", index=False)


# import pandas as pd

# # Load your Excel file
# df = pd.read_excel("C:\\Users\\ps200\\Desktop\\Prushal Tech\\Energy Transition\\energy_transition\\jan_hourly.xlsx")  # Update with actual path

# # Generate datetime range for each hour starting from 1st Sept 2024
# start_time = pd.Timestamp("2024-01-01 00:00")
# date_range = pd.date_range(start=start_time, periods=len(df), freq='h')
# df['Start_Time'] = date_range
# df['End_Time'] = df['Start_Time'] + pd.Timedelta(hours=1)

# # Format the Datetime column as "YYYY-MM-DD HH:MM - HH:MM"
# df['Datetime'] = df['Start_Time'].dt.strftime('%Y-%m-%d %H:%M') + " - " + df['End_Time'].dt.strftime('%H:%M')

# # Extract hour for filtering
# df['Hour'] = df['Start_Time'].dt.hour

# # Filter for peak hours (7–10 AM and 6–9 PM)
# peak_hours = [7, 8, 9, 10, 18, 19, 20, 21]
# peak_df = df[df['Hour'].isin(peak_hours)]

# # Select final columns
# peak_df = peak_df[['Datetime', 'Scada Hourly', 'System Hourly']]

# # Export to Excel
# peak_df.to_excel("jan_peak_hours_output.xlsx", index=False)
