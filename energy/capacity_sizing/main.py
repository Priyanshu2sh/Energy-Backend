import pypsa
import pandas as pd
# from .preprocessing import preprocess_multiple_profiles
from .setup_Components import setup_network
from .createModel import optimize_network
from .run_Optimizer import analyze_network_results
import gurobipy as gp
import logging

logger = logging.getLogger('debug_logger')  # Use the new debug logger


def optimization_model_capacity_sizing(input_data, hourly_demand=None, re_replacement=None, OA_cost=None, curtailment_selling_price=None, annual_curtailment_limit=None, peak_target=None, peak_hours=None, max_hours=None, transmission_capacity=None, monthly_availability=None):
    print("🚀 Starting optimization model...", input_data)
    sell_curtailment_percentage = annual_curtailment_limit

    ipp_name = None
    solar = None
    wind = None
    ess = None
    # if consumer_demand_path is not None:
    #     demand_file = pd.read_excel(consumer_demand_path)
    #     # Use direct hourly data, ensure index is datetime
    #     if not isinstance(demand_file.index, pd.DatetimeIndex):
    #         demand_file.index = pd.date_range(start='2022-01-01', periods=len(demand_file), freq='h')
    #     demand_data = demand_file.squeeze()
    # else:
    # Use direct hourly data from hourly_demand
    if not isinstance(hourly_demand.index, pd.DatetimeIndex):
        hourly_demand.index = pd.date_range(start='2022-01-01', periods=len(hourly_demand), freq='h')
    demand_data = hourly_demand.squeeze()

    # Use only user input (input_data) for the optimization
    results_dict = {}
    final_dict = input_data
    for ipp in final_dict:
        # keep track of which IPP we're processing so the final error/result keys are populated
        ipp_name = ipp
        solar_projects = final_dict[ipp].get('Solar', {})
        wind_projects = final_dict[ipp].get('Wind', {})
        ess_projects = final_dict[ipp].get('ESS', {})

        # Solar + Battery only (no wind)
        if solar_projects and ess_projects and not wind_projects:
            for solar_project in solar_projects:
                solar_profile = solar_projects[solar_project]['profile']
                # Use direct hourly profile, ensure index matches demand_data
                if not isinstance(solar_profile.index, pd.DatetimeIndex):
                    solar_profile.index = demand_data.index
                Solar_captialCost = solar_projects[solar_project]['capital_cost']
                Solar_marginalCost = solar_projects[solar_project]['marginal_cost']
                Solar_maxCapacity = solar_projects[solar_project]['max_capacity']
                solar_name = solar_project

                for ess_system in ess_projects:
                    Battery_captialCost = ess_projects[ess_system]['capital_cost']
                    Battery_marginalCost = ess_projects[ess_system]['marginal_cost']
                    Battery_Eff_store = ess_projects[ess_system]['efficiency']
                    Battery_Eff_dispatch = ess_projects[ess_system]['efficiency']
                    DoD = ess_projects[ess_system]['DoD']
                    # Battery_max_energy_capacity = ess_projects[ess_system].get('max_energy_capacity', None)
                    Battery_standing_loss = ess_projects[ess_system].get('standing_loss', None)
                    auxiliary_consumption = ess_projects[ess_system].get('auxiliary_consumption', None)
                    auxiliary_tariff = ess_projects[ess_system].get('auxiliary_tariff', None)
                    ess_name = ess_system

                    # Add auxiliary cost to battery marginal cost
                    if auxiliary_consumption is not None and auxiliary_tariff is not None:
                        Battery_marginalCost += auxiliary_consumption * auxiliary_tariff * 1000
                    else:
                        print("Warning: auxiliary_consumption or auxiliary_tariff is None. Skipping auxiliary cost calculation.")

                    # Pass to setup_network
                    network = setup_network(
                        demand_data=demand_data,
                        solar_profile=solar_profile,
                        Solar_maxCapacity=Solar_maxCapacity,
                        Solar_captialCost=Solar_captialCost,
                        Solar_marginalCost=Solar_marginalCost,
                        Battery_captialCost=Battery_captialCost,
                        Battery_marginalCost=Battery_marginalCost,
                        Battery_Eff_store=Battery_Eff_store,
                        Battery_Eff_dispatch=Battery_Eff_dispatch,
                        Battery_standing_loss=Battery_standing_loss,
                        ess_name=ess_name,
                        solar_name=solar_name,
                        max_hours=max_hours,  # Add this
                        transmission_capacity=transmission_capacity
                    )

                    # Pass to optimize_network
                    # Pass to optimize_network
                    m = optimize_network(
                        network=network,
                        solar_profile=solar_profile,
                        demand_data=demand_data,
                        Solar_maxCapacity=Solar_maxCapacity,
                        Solar_captialCost=Solar_captialCost,
                        Battery_captialCost=Battery_captialCost,
                        Solar_marginalCost=Solar_marginalCost,
                        Battery_marginalCost=Battery_marginalCost,
                        sell_curtailment_percentage=sell_curtailment_percentage,
                        curtailment_selling_price=curtailment_selling_price,
                        DO=re_replacement/100 if re_replacement else 0.65,
                        DoD=DoD,
                        annual_curtailment_limit=annual_curtailment_limit,
                        ess_name=ess_name,
                        peak_target=peak_target,
                        peak_hours=peak_hours,
                        max_hours=max_hours,
                        transmission_capacity=transmission_capacity,
                        monthly_availability=monthly_availability
                    )

                    print("🔧 Optimization model created and solved.")
                    analyze_network_results(
                        network=network,
                        sell_curtailment_percentage=sell_curtailment_percentage,
                        curtailment_selling_price=curtailment_selling_price,
                        solar_profile=solar_profile,
                        results_dict=results_dict,
                        OA_cost=OA_cost,
                        ess_name=ess_name,
                        solar_name=solar_name,
                        ipp_name=ipp_name,
                        max_hours=max_hours,
                                        transmission_capacity=transmission_capacity,
                                        monthly_availability=monthly_availability
                    )

    # Convert results_dict to DataFrame for easy sorting and return full dict
    if results_dict:
        res_df = pd.DataFrame.from_dict(results_dict, orient='index')
        # Sort by 'Per Unit Cost'
        sorted_results = res_df.sort_values(by='Per Unit Cost')
        # Convert to dictionary with index as keys
        sorted_dict = sorted_results.to_dict(orient="index")
        return sorted_dict
    else:
        return {"error": "The demand cannot be met by the IPPs",
                "ipp": ipp_name,
                "solar": solar,
                "wind": wind,
                "ess": ess}

# response_data = optimization_model(input_data, hourly_demand=numeric_hourly_demand, re_replacement=re_replacement, valid_combinations=valid_combinations, OA_cost=OA_cost)