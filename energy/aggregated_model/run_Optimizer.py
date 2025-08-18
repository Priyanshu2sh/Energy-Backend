import traceback
import numpy as np
import pandas as pd
import logging

# Get the logger that is configured in the settings
traceback_logger = logging.getLogger('django')
logger = logging.getLogger('debug_logger')  # Use the new debug logger

def analyze_network_results(network=None, sell_curtailment_percentage=None, curtailment_selling_price=None,
                            solar_profile=None, wind_profile=None, results_dict=None, OA_cost=None,
                            ess_name=None, solar_name=None, wind_name=None, ipp_name=None):
  # if solar_profile is not None and not solar_profile.empty:
  #  solar_name = solar_profile.name
  # if wind_profile is not None and not wind_profile.empty:
  #  wind_name = wind_profile.name

  try:
      # Solve the optimization model
      lopf_status = network.optimize.solve_model()
      if lopf_status[1] == "infeasible":
          raise ValueError("Optimization returned 'infeasible' status.")

      # Initialize placeholders for results
      gross_energy_generation = 0
      gross_energy_allocation = 0
      solar_wind_allocation = 0
      solar_allocation = 0
      wind_allocation = 0

      # Demand profile
      demand = network.loads_t.p_set.sum(axis=1)
      # Handle Solar
      if "Solar" in network.generators.index:
          solar_allocation = network.generators_t.p["Solar"]
          solar_capacity = network.generators.at["Solar", "p_nom_opt"]
          solar_generation = network.generators_t.p_max_pu["Solar"] * solar_capacity
          gross_energy_generation += solar_generation
          gross_energy_allocation += solar_allocation
          solar_wind_allocation += solar_allocation

          # Solar costs
          solar_capital_cost = solar_capacity * network.generators.at["Solar", "capital_cost"]
          solar_marginal_cost = (solar_allocation * network.generators.at["Solar", "marginal_cost"]).sum(axis=0) * 2
          total_solar_cost = solar_capital_cost + solar_marginal_cost
      else:
          solar_capacity = 0
          solar_capital_cost = 0
          solar_marginal_cost = 0
          total_solar_cost = 0

      # Handle Wind
      if "Wind" in network.generators.index:
          wind_allocation = network.generators_t.p["Wind"]
          wind_capacity = network.generators.at["Wind", "p_nom_opt"]
          wind_generation = network.generators_t.p_max_pu["Wind"] * wind_capacity
          gross_energy_generation += wind_generation
          gross_energy_allocation += wind_allocation
          solar_wind_allocation += wind_allocation

          # Wind costs
          wind_capital_cost = wind_capacity * network.generators.at["Wind", "capital_cost"]
          wind_marginal_cost = (wind_allocation * network.generators.at["Wind", "marginal_cost"]).sum(axis=0) * 2
          total_wind_cost = wind_capital_cost + wind_marginal_cost
      else:
          wind_capacity = 0
          total_wind_cost = 0
          wind_capital_cost = 0
          wind_marginal_cost = 0

      # Battery SOC, Discharge, Charge
      if ess_name is not None:
          battery_soc = network.storage_units_t.state_of_charge["Battery"]
          ess_discharge = network.storage_units_t.p_dispatch["Battery"]
          ess_discharge[abs(ess_discharge) < 1e-5] = 0
          ess_charge = network.storage_units_t.p_store["Battery"]
          gross_energy_allocation += (ess_discharge - ess_charge)
          ess_capacity = network.storage_units.at["Battery", "p_nom_opt"]
          ess_capital_cost = ess_capacity * network.storage_units.at["Battery", "capital_cost"]
          ess_marginal_cost = ((((network.storage_units_t.p_dispatch["Battery"] * network.storage_units.at["Battery", "marginal_cost"]).sum(axis=0)) + ((network.storage_units_t.p_store["Battery"] * network.storage_units.at["Battery", "marginal_cost"]).sum(axis=0)))) * 2
          total_ess_cost = ess_capital_cost + ess_marginal_cost
      else:
          ess_capacity = 0
          battery_soc = 0
          ess_discharge = 0
          ess_charge = 0
          ess_capital_cost = 0
          ess_marginal_cost = 0
          total_ess_cost = 0

      # Unmet demand and total demand met by allocation
      virtual_gen = network.generators_t.p['Unmet_Demand']
      demand_met = np.where(virtual_gen > 0, "No", "Yes")

  # Curtailment calculations
      gross_curtailment = gross_energy_generation - solar_wind_allocation
      gross_curtailment[gross_curtailment < 0] = 0
      # gross_curtailment[abs(ess_discharge) < 1e-5] = 0
      annual_curtailment = gross_curtailment.sum() * 2
      gross_curtailment_marginal=0

      # Curtailment costs
      if "Solar" in network.generators.index:
          solar_curtailment = (network.generators_t.p_max_pu['Solar'] * solar_capacity) - solar_allocation
          solar_curtailment[solar_curtailment < 0] = 0
          gross_curtailment_marginal += solar_curtailment * network.generators.at["Solar", "marginal_cost"]
        # solar_curtailment = gross_curtailment * (solar_generation / gross_energy_generation)
        # solar_curtailment_cost = (solar_curtailment * network.generators.at["Solar", "marginal_cost"]).sum(axis=0)
      else:
          solar_curtailment = 0

      if "Wind" in network.generators.index:
          wind_curtailment = (network.generators_t.p_max_pu['Wind'] * wind_capacity) - wind_allocation
          wind_curtailment[wind_curtailment < 0] = 0
          gross_curtailment_marginal += wind_curtailment * network.generators.at["Wind", "marginal_cost"]
        #  wind_curtailment = gross_curtailment * (wind_generation / gross_energy_generation)
        # wind_curtailment_cost = (wind_curtailment * network.generators.at["Wind", "marginal_cost"]).sum(axis=0)
      else:
          wind_curtailment = 0

      sell_curtailment = sell_curtailment_percentage * (solar_curtailment + wind_curtailment) * curtailment_selling_price
      total_curtailment_cost = (gross_curtailment_marginal - sell_curtailment).sum(axis=0) * 2



      # Total cost calculation
      total_cost = total_solar_cost + total_wind_cost + total_curtailment_cost + total_ess_cost
      annual_demand_met = gross_energy_allocation.sum() * 2
      per_unit_cost = total_cost / annual_demand_met if annual_demand_met > 0 else float('inf')
      annual_demand_offset = 100 -  (virtual_gen.sum() / network.loads_t.p_set.sum().sum()) * 100
      annual_generation = gross_energy_generation.sum() * 2
      excess_percentage = (annual_curtailment / annual_generation) * 100
      annual_demand = demand.sum() * 2
      OA_cost=OA_cost
      Final_cost=OA_cost + per_unit_cost
      objective_for_aggregate_cost = network.objective * 2

      # Create Results DataFrame
      results_df = pd.DataFrame({
          "Demand": demand,
          "Solar Allocation": solar_allocation if isinstance(solar_allocation, pd.Series) else 0,
          "Wind Allocation": wind_allocation if isinstance(wind_allocation, pd.Series) else 0,
          "SOC": battery_soc,
          "ESS Discharge": ess_discharge,
          "ESS Charge": ess_charge,
          "Unmet demand": virtual_gen,
          "Generation": gross_energy_generation.squeeze(),
          "Curtailment": gross_curtailment,
          "Total Demand met by allocation": gross_energy_allocation,
          "Demand met": demand_met
      })
      # logger.debug(f"Results DataFrame:\n{results_df}")

      # Print outputs
      # logger.debug(f"\nOptimal Capacities:")
      # logger.debug(f"Optimal Solar Capacity: {solar_capacity:.2f} MW")
      # logger.debug(f"Optimal Wind Capacity: {wind_capacity:.2f} MW")
      # logger.debug(f"Optimal Battery Capacity: {ess_capacity:.2f} MW")
      # logger.debug(f"Annual Demand Offset: {annual_demand_offset:.2f}%")
      # logger.debug(f"Annual Demand: {annual_demand :.2f}")
      # logger.debug(f"Annual Generation: {annual_generation:.2f}")
      # logger.debug(f"Annual Demand met: {annual_demand_met:.2f}")
      # logger.debug(f"Total Solar Cost: {total_solar_cost:.2f} (Capital: {solar_capital_cost:.2f}, Marginal: {solar_marginal_cost:.2f})")
      # logger.debug(f"Total Wind Cost: {total_wind_cost:.2f} (Capital: {wind_capital_cost:.2f}, Marginal: {wind_marginal_cost:.2f})")
      # logger.debug(f"Total ESS Cost: {total_ess_cost:.2f} (Capital: {ess_capital_cost:.2f}, Marginal: {ess_marginal_cost:.2f})")
      # logger.debug(f"Total Curtailment Cost: {total_curtailment_cost:.2f}")
      # logger.debug(f"Total Cost: {total_cost:.2f}")
      # logger.debug(f"Per unit cost: {per_unit_cost:.2f}")
      # logger.debug(f"Final Cost: {Final_cost:.2f}")
      # logger.debug(f"Annual Curtailment: {excess_percentage:.2f}%")
      # logger.debug(f"Total objective cost: {objective_for_aggregate_cost:.2f}")

      if solar_name is not None and wind_name is None and ess_name is not None:
        key =f"{ipp_name}-{solar_name}-{ess_name}"
      elif solar_name is None and wind_name is not None  and ess_name is not None:
        key =f"{ipp_name}-{wind_name}-{ess_name}"
      elif solar_name is not None and wind_name is not None  and ess_name is not None:
        key =f"{ipp_name}-{solar_name}-{wind_name}-{ess_name}"
      elif solar_name is not None and wind_name is None  and ess_name is None:
        key =f"{ipp_name}-{solar_name}"
      elif solar_name is None and wind_name is not None  and ess_name is None:
        key =f"{ipp_name}-{wind_name}"
      elif solar_name is not None and wind_name is not None and ess_name is None:
        key =f"{ipp_name}-{solar_name}-{wind_name}"
      else:
        key ="No generation technology added"

      results_dict[key] = {
                  "Optimal Solar Capacity (MW)": solar_capacity,
                  "Optimal Wind Capacity (MW)": wind_capacity,
                  "Optimal Battery Capacity (MW)": ess_capacity,
                  "Per Unit Cost": per_unit_cost,
                  "Final Cost": Final_cost,
                  "Total Cost": total_cost,
                  "Annual Demand Offset": annual_demand_offset,
                  "Annual Demand Met": annual_demand_met,
                  "Annual Curtailment": excess_percentage,

                  "Demand": [round(val, 2) for val in demand],
                  "Solar Allocation": solar_allocation if isinstance(solar_allocation, pd.Series) else 0,
                  "Wind Allocation": wind_allocation if isinstance(wind_allocation, pd.Series) else 0,
                  "SOC": battery_soc,
                  "ESS Discharge": ess_discharge,
                  "ESS Charge": ess_charge,
                  "Unmet demand": virtual_gen,
                  "Generation": gross_energy_generation.squeeze(),
                  "Curtailment": [round(val, 2) for val in gross_curtailment],
                  "Total Demand met by allocation": gross_energy_allocation,
                  "Demand met": demand_met

              }
      # results_df.to_excel(f"results_{key}.xlsx", index=False)
      # logger.debug(f"{key} - Optimization successful.")
      # logger.debug(results_dict)

      # logger.debug("Optimization completed successfully.")

  except ValueError as ve:
    logger.debug(" ")

  except Exception as e:
    tb = traceback.format_exc()  # Get the full traceback
    traceback_logger.error(f"Exception: {str(e)}\nTraceback:\n{tb}")  # Log error with traceback
    logger.debug(f"An unexpected error occurred during optimization: {e}")





