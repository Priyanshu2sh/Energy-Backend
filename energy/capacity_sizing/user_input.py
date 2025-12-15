import pandas as pd
import os
from .main import optimization_model_capacity_sizing

def apply_degradation(df, degradation_pct, years):
    """Apply yearly degradation across full hourly dataset."""
    frames = []
    for y in range(years):
        degraded_df = df * ((1 - (degradation_pct[0] / 100)) ** y)
        degraded_df = degraded_df.reset_index(drop=True)
        frames.append(degraded_df)
    return pd.concat(frames, ignore_index=True)

def main(
    PPA_capacity: float,  # Required
    transmission_capacity: float,  # Required
    solar_profiles: list = None,  # Optional, list of dicts with profile info
    wind_profiles: list = None,  # Optional, list of dicts with profile info
    battery_systems: list = None,  # Optional, list of dicts with battery info
    demand_file: str = None,  # Optional, path to demand Excel file
    PPA_tenure_years: int = 1,  # Optional with default
    solar_degradation: float = 0.0,  # Optional with default
    wind_degradation: float = 0.0,  # Optional with default
    battery_degradation: float = 0.0,  # Optional with default
    battery_max_hours: float = 4,  # Optional with default
    OA_cost: float = 1000,  # Optional with default
    curtailment_selling_price: float = 3000,  # Optional with default
    sell_curtailment_percentage: float = 0.5,  # Optional with default
    annual_curtailment_limit: float = 0.3,  # Optional with default
    re_replacement: float = 65,  # Optional with default
    peak_target: float = 0.9,  # Optional with default
    peak_hours: list = None  # Optional, list of peak hours
):
    """
    Main function for EXG Optimizer with parameterized inputs.
    
    Required Parameters:
    - PPA_capacity (float): PPA Capacity in MW
    - transmission_capacity (float): Transmission Connectivity Capacity in MW
    
    Optional Parameters:
    - solar_profiles (list): List of dicts containing solar profile information
    - wind_profiles (list): List of dicts containing wind profile information
    - battery_systems (list): List of dicts containing battery system information
    - demand_file (str): Path to demand Excel file
    - PPA_tenure_years (int): PPA Tenure in years (default: 1)
    - solar_degradation (float): Solar degradation per year in % (default: 0.0)
    - wind_degradation (float): Wind degradation per year in % (default: 0.0)
    - battery_degradation (float): Battery degradation per year in % (default: 0.0)
    - battery_max_hours (float): Battery max hours (default: 4)
    - OA_cost (float): OA cost (default: 1000)
    - curtailment_selling_price (float): Curtailment selling price (default: 3000)
    - sell_curtailment_percentage (float): Sell curtailment percentage 0-1 (default: 0.5)
    - annual_curtailment_limit (float): Annual curtailment limit 0-1 (default: 0.3)
    - re_replacement (float): RE replacement percentage 0-100 (default: 65)
    - peak_target (float): RE replacement percentage for peak hours (default: 0.9)
    - peak_hours (list): List of peak hours (default: None)
    """
    
    print("=== EXG Optimizer User Input ===")

    # Initialize default peak hours if not provided
    if peak_hours is None:
        peak_hours = [6, 7, 8, 18, 19, 20]  # Default peak hours

    # Handle demand data
    if demand_file and os.path.isfile(demand_file):
        hourly_demand = pd.read_excel(demand_file)
    else:
        print("\nNo demand file provided or file not found.")
        print(f"Using flat demand based on PPA Capacity = {PPA_capacity} MW for 24 hours.")
        hourly_demand = pd.DataFrame({'Demand': [PPA_capacity] * 24})
        demand_file = None 

    # === Extend Demand for PPA Tenure Years ===
    hours_per_year = 24 * 365
    base_hours = len(hourly_demand)

    if base_hours == 24:
        hourly_demand = pd.concat([hourly_demand] * 365, ignore_index=True)
        print(f"Base hourly demand expanded for 1 year = {len(hourly_demand)} rows")

    extended_demand = pd.concat([hourly_demand] * PPA_tenure_years, ignore_index=True)

    if demand_file:
        extended_demand['Demand'] += PPA_capacity

    print(f"Total extended demand rows: {len(extended_demand)} (expected {hours_per_year * PPA_tenure_years})")

    # === Apply degradation and build input data ===
    input_data = {'IPP1': {}}
    solar_gen_all = pd.DataFrame()
    wind_gen_all = pd.DataFrame()
    
    if solar_profiles:
        input_data['IPP1']['Solar'] = {}
        for idx, s in enumerate(solar_profiles):
            if 'path' not in s or not os.path.isfile(s['path']):
                raise ValueError(f"Invalid path in solar profile {idx+1}")
            
            base_df = pd.read_excel(s['path']).squeeze()
            if len(base_df) == 24:
                base_df = pd.concat([base_df] * hours_per_year, ignore_index=True)
            profile_df = apply_degradation(base_df, solar_degradation, PPA_tenure_years)
            input_data['IPP1']['Solar'][f'Solar_{idx+1}'] = {
                'profile': profile_df,
                'max_capacity': s['max_capacity'],
                'capital_cost': s['capital_cost'],
                'marginal_cost': s['marginal_cost']
            }
            solar_gen_all[f'Solar_{idx+1}'] = profile_df.reset_index(drop=True)
        
        if not solar_gen_all.empty:
            solar_gen_all.to_excel("extended_solar_generation.xlsx", index=False)
            print("✅ Solar generation file saved as 'extended_solar_generation.xlsx'")

    if wind_profiles:
        input_data['IPP1']['Wind'] = {}
        for idx, w in enumerate(wind_profiles):
            if 'path' not in w or not os.path.isfile(w['path']):
                raise ValueError(f"Invalid path in wind profile {idx+1}")
            
            base_df = pd.read_excel(w['path']).squeeze()
            if len(base_df) == 24:
                base_df = pd.concat([base_df] * hours_per_year, ignore_index=True)
            profile_df = apply_degradation(base_df, wind_degradation, PPA_tenure_years)
            input_data['IPP1']['Wind'][f'Wind_{idx+1}'] = {
                'profile': profile_df,
                'max_capacity': w['max_capacity'],
                'capital_cost': w['capital_cost'],
                'marginal_cost': w['marginal_cost']
            }
            wind_gen_all[f'Wind_{idx+1}'] = profile_df.reset_index(drop=True)
        
        if not wind_gen_all.empty:
            wind_gen_all.to_excel("extended_wind_generation.xlsx", index=False)
            print("✅ Wind generation file saved as 'extended_wind_generation.xlsx'")

    if battery_systems:
        input_data['IPP1']['ESS'] = {}
        for idx, b in enumerate(battery_systems):
            required_keys = ['capital_cost', 'marginal_cost', 'efficiency', 'DoD', 'max_energy_capacity']
            if not all(key in b for key in required_keys):
                raise ValueError(f"Missing required keys in battery system {idx+1}")
            
            input_data['IPP1']['ESS'][f'ESS_{idx+1}'] = {
                'capital_cost': b['capital_cost'],
                'marginal_cost': b['marginal_cost'],
                'efficiency': b['efficiency'],
                'DoD': b['DoD'],
                'max_energy_capacity': b['max_energy_capacity'],
                'battery_degradation': battery_degradation
            }

    # === Save Extended Input Data ===
    extended_demand.to_excel("extended_demand.xlsx", index=False)
    print("✅ Extended demand file saved as 'extended_demand.xlsx'")

    # === Run Optimization ===
    result = optimization_model_capacity_sizing(
        input_data=input_data,
        consumer_demand_path=demand_file,
        hourly_demand=extended_demand,
        re_replacement=re_replacement,
        OA_cost=OA_cost,
        curtailment_selling_price=curtailment_selling_price,
        sell_curtailment_percentage=sell_curtailment_percentage,
        annual_curtailment_limit=annual_curtailment_limit,
        peak_target=peak_target,
        peak_hours=peak_hours,
        battery_max_hours=battery_max_hours
    )

    print("\n=== Optimization Result ===")
    print(result)

    print("\n✅ You can download the generated files:")
    print("   - extended_demand.xlsx")
    if not solar_gen_all.empty:
        print("   - extended_solar_generation.xlsx")
    if not wind_gen_all.empty:
        print("   - extended_wind_generation.xlsx")
    
    return result

if __name__ == "__main__":
    # Example usage with required and optional parameters
    result = main(
        # Required parameters
        PPA_capacity=100.0,
        transmission_capacity=120.0,
        
        # Optional parameters with profiles
        solar_profiles=[{
            'path': 'path/to/solar_profile.xlsx',
            'max_capacity': 150.0,
            'capital_cost': 40000000,
            'marginal_cost': 0
        }],
        wind_profiles=[{
            'path': 'path/to/wind_profile.xlsx',
            'max_capacity': 100.0,
            'capital_cost': 50000000,
            'marginal_cost': 0
        }],
        battery_systems=[{
            'capital_cost': 30000000,
            'marginal_cost': 100,
            'efficiency': 0.85,
            'DoD': 0.8,
            'max_energy_capacity': 50.0
        }],
        
        # Other optional parameters with defaults
        demand_file='path/to/demand.xlsx',  # Optional
        PPA_tenure_years=25,  # Default: 1
        solar_degradation=0.5,  # Default: 0.0
        wind_degradation=0.3,  # Default: 0.0
        battery_degradation=1.0,  # Default: 0.0
        battery_max_hours=4,  # Default: 4
        OA_cost=1000,  # Default: 1000
        curtailment_selling_price=3000,  # Default: 3000
        sell_curtailment_percentage=0.5,  # Default: 0.5
        annual_curtailment_limit=0.3,  # Default: 0.3
        re_replacement=65,  # Default: 65
        peak_target=0.9,  # Default: 0.9
        peak_hours=[6, 7, 8, 18, 19, 20]  # Default: [6, 7, 8, 18, 19, 20]
    )
