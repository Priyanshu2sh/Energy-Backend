import traceback
import numpy as np
import pandas as pd
import logging
import time
from pathlib import Path

# Get the logger that is configured in the settings
traceback_logger = logging.getLogger('django')
logger = logging.getLogger('debug_logger')  # Use the new debug logger

def analyze_network_results(network=None, sell_curtailment_percentage=None, curtailment_selling_price=None,
                            solar_profile=None, wind_profile=None, results_dict=None, OA_cost=None,
                            ess_name=None, solar_name=None, wind_name=None, ipp_name=None, max_hours=None, transmission_capacity=None, monthly_availability=None):
  
  if solar_profile is not None and not solar_profile.empty:
   solar_name = solar_name
  if wind_profile is not None and not wind_profile.empty:
   wind_name = wind_name

  try:
      # Solve the optimization model
      lopf_status = network.optimize.solve_model()
      if lopf_status[1] == "infeasible":
          raise ValueError("Optimization returned 'infeasible' status.")

      # Assign shadow prices (duals) to the network
      network.optimize.assign_duals()

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
          solar_marginal_cost = (solar_allocation * network.generators.at["Solar", "marginal_cost"]).sum(axis=0) 
          total_solar_cost = solar_marginal_cost #solar_capital_cost + solar_marginal_cost
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
          wind_marginal_cost = (wind_allocation * network.generators.at["Wind", "marginal_cost"]).sum(axis=0)
          total_wind_cost =wind_marginal_cost # wind_capital_cost + wind_marginal_cost
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
          ess_capacity = network.storage_units.at["Battery", "p_nom_opt"]
          
          # Only calculate max_battery_energy if max_hours is provided
          if max_hours is not None:
              max_battery_energy = ess_capacity * max_hours
          else:
              max_battery_energy = None
          
          ess_capital_cost = ess_capacity * network.storage_units.at["Battery", "capital_cost"]
          ess_marginal_cost = (
              (network.storage_units_t.p_dispatch["Battery"] * network.storage_units.at["Battery", "marginal_cost"]).sum(axis=0) +
              (network.storage_units_t.p_store["Battery"] * network.storage_units.at["Battery", "marginal_cost"]).sum(axis=0)
          )
          total_ess_cost = ess_marginal_cost #ess_capital_cost + ess_marginal_cost
      else:
          ess_capacity = 0
          battery_soc = 0
          ess_discharge = 0
          ess_charge = 0
          ess_capital_cost = 0
          ess_marginal_cost = 0
          total_ess_cost = 0
          max_battery_energy = None
        
      total_allocated = solar_allocation + wind_allocation + (ess_discharge - ess_charge)

      if transmission_capacity is not None:
        transmitted = np.minimum(total_allocated, transmission_capacity)
      else:
        transmitted = total_allocated

      # Calculate generator-level curtailment (waste at source, before transmission)
      gross_curtailment = 0
      if "Solar" in network.generators.index:
          gross_curtailment += solar_generation - solar_allocation
      if "Wind" in network.generators.index:
          gross_curtailment += wind_generation - wind_allocation
      gross_curtailment[gross_curtailment < 0] = 0  # Ensure non-negative

      # If transmission limits transmitted power, add extra curtailment (e.g., if total_allocated > transmitted, excess is wasted)
      transmission_curtailment = np.maximum(0, total_allocated - transmitted)
      gross_curtailment += transmission_curtailment

      # Calculate sellable excess (transmitted power exceeding demand, for revenue)
      sellable = np.maximum(0, transmitted - demand)
      

      print(f"Debug - Excess Generation (sellable): {np.sum(sellable)}")
      print(f"Debug - Total Allocated: {np.sum(total_allocated)}")
      print(f"Debug - Transmitted: {np.sum(transmitted)}")
      print(f"Debug - Gross Curtailment: {np.sum(gross_curtailment)}")
      print(f"Debug - ESS Charge: {np.sum(ess_charge)}")

      gross_curtailment_marginal = 0
      if "Solar" in network.generators.index:
          solar_curtailment = (network.generators_t.p_max_pu['Solar'] * solar_capacity) - solar_allocation
          solar_curtailment[solar_curtailment < 0] = 0
          gross_curtailment_marginal += solar_curtailment * network.generators.at["Solar", "marginal_cost"]
      if "Wind" in network.generators.index:
          wind_curtailment = (network.generators_t.p_max_pu['Wind'] * wind_capacity) - wind_allocation
          wind_curtailment[wind_curtailment < 0] = 0
          gross_curtailment_marginal += wind_curtailment * network.generators.at["Wind", "marginal_cost"]
    
      sell_curtailment = sell_curtailment_percentage * sellable * curtailment_selling_price
      # Total curtailment cost
      total_curtailment_cost = (gross_curtailment_marginal - sell_curtailment).sum(axis=0)

      # Total cost calculation
      print("Debug - Cost Components:")
      print(f"  Solar Capital Cost: {solar_capital_cost}")
      print(f"  Solar Marginal Cost: {solar_marginal_cost}")
      print(f"  Wind Capital Cost: {wind_capital_cost}")
      print(f"  Wind Marginal Cost: {wind_marginal_cost}")
      print(f"  ESS Capital Cost: {ess_capital_cost}")
      print(f"  ESS Marginal Cost: {ess_marginal_cost}")
      print(f"  Curtailment Cost: {total_curtailment_cost}")
      total_cost = total_solar_cost + total_wind_cost + total_curtailment_cost + total_ess_cost

      print(f"  Total Cost: {total_cost}")
      # annual_demand_met = gross_energy_allocation.sum()  # OLD: Overestimates

      virtual_gen = np.maximum(0, demand - transmitted)
      demand_met = np.minimum(demand, transmitted)

      # -------------------------
      # Monthly fulfillment summary
      # -------------------------
      try:
          # Aggregate by calendar month across the whole time series (sums all years together)
          monthly_demand = demand.groupby(demand.index.month).sum()
          monthly_transmitted = pd.Series(transmitted, index=demand.index).groupby(demand.index.month).sum()
          monthly_met = demand_met.groupby(demand.index.month).sum()

          percent_met = (monthly_met / monthly_demand.replace({0: np.nan})) * 100
          percent_met = percent_met.fillna(0)

          # Prepare target percentages if provided
          target_pct = None
          meets_target = None
          if monthly_availability is not None:
              # Normalize input to length-12 list of percentages (0-100)
              if isinstance(monthly_availability, (list, tuple, pd.Series)):
                  targets = list(monthly_availability)
              else:
                  targets = [monthly_availability]
              # Expand single-value target to 12 months
              if len(targets) == 1:
                  targets = targets * 12
              # Convert fractions (0-1) to percentages and ensure values are in 0-100
              normalized = []
              for t in targets:
                  try:
                      val = float(t)
                  except Exception:
                      val = 0.0
                  if val <= 1:
                      val = val * 100
                  normalized.append(val)
              target_pct = pd.Series(normalized, index=range(1, 13))

              # Compare percent_met (index 1..12) to target_pct
              meets_target = percent_met >= target_pct

          # Build monthly summary DataFrame
          monthly_summary = pd.DataFrame({
              'Month': percent_met.index,
              'Demand (MWh)': monthly_demand.values,
              'Transmitted (MWh)': monthly_transmitted.values,
              'Met (MWh)': monthly_met.values,
              'Percent Met (%)': percent_met.values
          })
          if target_pct is not None:
              monthly_summary['Target (%)'] = target_pct.values
              monthly_summary['Meets Target'] = meets_target.values

          # Save monthly summary to Excel
          monthly_path = Path("optimization_monthly_summary.xlsx")
          for attempt in range(3):
              try:
                  monthly_summary.to_excel(monthly_path, index=False)
                  break
              except PermissionError:
                  logger.error(f"Attempt {attempt + 1}: Unable to write to {monthly_path}. Ensure the file is not open.")
                  if attempt < 2:
                      time.sleep(2)
                  else:
                      raise

          # Print a concise monthly summary to console
          print("\n=== Monthly Fulfillment Summary ===")
          print(monthly_summary)

      except Exception as me_err:
          logger.debug(f"Could not compute monthly summary: {me_err}")

      
      annual_demand_met = demand_met.sum()  # NEW: Actual met demand
      per_unit_cost = total_cost / annual_demand_met if annual_demand_met > 0 else float('inf')

      # Define unmet (virtual) generation as unmet demand and demand met by allocation
      # virtual_gen: energy not met (demand > transmitted)
      # demand_met: energy met (min of demand and transmitted)
      virtual_gen = np.maximum(0, demand - transmitted)
      demand_met = np.minimum(demand, transmitted)

      # Annual demand offset as percentage of unmet demand relative to total annual demand
      total_annual_demand = network.loads_t.p_set.sum().sum() if hasattr(network, "loads_t") else demand.sum()
      annual_demand_offset = 100 - (virtual_gen.sum() / total_annual_demand) * 100 if total_annual_demand > 0 else 0

      # annual_generation = gross_energy_generation.sum() * 2
      annual_generation = gross_energy_generation.sum()
      # Annual curtailment (sum of hourly curtailment)
      annual_curtailment = gross_curtailment.sum()
      excess_percentage = (annual_curtailment / annual_generation) * 100 if annual_generation > 0 else 0

      # annual_demand = demand.sum() * 2
      annual_demand = demand.sum()
      # Battery total capacity in MWh (use max_battery_energy calculated earlier or 0)
      battery_cap = max_battery_energy

      OA_cost = OA_cost
      Final_cost = OA_cost + per_unit_cost
      # objective_for_aggregate_cost = network.objective * 2
      objective_for_aggregate_cost = network.objective 

      # Define the annual summary dictionary with units
      annual_summary = {
          "Optimal Solar Capacity (MW)": solar_capacity,
          "Optimal Wind Capacity (MW)": wind_capacity,
          "Optimal Battery Capacity (MW)": ess_capacity,
          "Battery total Capacity (MWh)": battery_cap,
          "Per Unit Cost (INR/MWh)": per_unit_cost,
          "Final Cost (INR)": Final_cost,
          "Total Cost (INR)": total_cost,
          "Annual Demand Offset (%)": annual_demand_offset,
          "Annual Demand Met (MWh)": annual_demand_met,
          "Annual Curtailment (%)": excess_percentage,
          "Annual Generation (MWh)": annual_generation,
          "Annual Demand (MWh)": annual_demand,
          "OA Cost (INR)": OA_cost,
          "Objective Aggregate Cost (INR)": objective_for_aggregate_cost
      }
      
      # Only add max_hours to summary if it's not None (i.e., C rating was not NA)
      if max_hours is not None:
          annual_summary["Battery max hours (h)"] = max_hours

      # Create Results DataFrame (hourly results)
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
      # Save hourly results to Excel
      results_df.to_excel("optimization_hourly_results.xlsx", index=True)

      # Save annual summary to separate Excel file with error handling
      annual_summary_path = Path("optimization_annual_summary.xlsx")
      for attempt in range(3):  # Retry up to 3 times
          try:
              pd.DataFrame([annual_summary]).to_excel(annual_summary_path, index=False)
              break  # Exit loop if successful
          except PermissionError as e:
              logger.error(f"Attempt {attempt + 1}: Unable to write to {annual_summary_path}. Ensure the file is not open.")
              if attempt < 2:  # Retry for the first two attempts
                  time.sleep(2)  # Wait for 2 seconds before retrying
              else:
                  raise e  # Raise the error after 3 failed attempts

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
     

      attributes_dict = {}
      if "Solar" in network.generators.index:
            solar_attrs = {
                'p_nom_opt': network.generators.at["Solar", "p_nom_opt"],
                'p': network.generators_t.p["Solar"],
            }
            # Add shadow prices if available
            if 'mu_upper' in network.generators_t and "Solar" in network.generators_t.mu_upper.columns:
                solar_attrs['mu_upper'] = network.generators_t.mu_upper["Solar"]
            if 'mu_lower' in network.generators_t and "Solar" in network.generators_t.mu_lower.columns:
                solar_attrs['mu_lower'] = network.generators_t.mu_lower["Solar"]
            if 'mu_p_set' in network.generators_t and "Solar" in network.generators_t.mu_p_set.columns:
                solar_attrs['mu_p_set'] = network.generators_t.mu_p_set["Solar"]
            if 'mu_ramp_limit_up' in network.generators_t and "Solar" in network.generators_t.mu_ramp_limit_up.columns:
                solar_attrs['mu_ramp_limit_up'] = network.generators_t.mu_ramp_limit_up["Solar"]
            if 'mu_ramp_limit_down' in network.generators_t and "Solar" in network.generators_t.mu_ramp_limit_down.columns:
                solar_attrs['mu_ramp_limit_down'] = network.generators_t.mu_ramp_limit_down["Solar"]
            # Committable attributes (if committable=True was set, but in this model it's not)
            if 'status' in network.generators_t and "Solar" in network.generators_t.status.columns:
                solar_attrs['status'] = network.generators_t.status["Solar"]
            if 'start_up' in network.generators_t and "Solar" in network.generators_t.start_up.columns:
                solar_attrs['start_up'] = network.generators_t.start_up["Solar"]
            if 'shut_down' in network.generators_t and "Solar" in network.generators_t.shut_down.columns:
                solar_attrs['shut_down'] = network.generators_t.shut_down["Solar"]
            attributes_dict['Solar'] = pd.DataFrame(solar_attrs)

      # For Wind Generator
      if "Wind" in network.generators.index:
            wind_attrs = {
                'p_nom_opt': network.generators.at["Wind", "p_nom_opt"],
                'p': network.generators_t.p["Wind"],
            }
            # Add shadow prices if available
            if 'mu_upper' in network.generators_t and "Wind" in network.generators_t.mu_upper.columns:
                wind_attrs['mu_upper'] = network.generators_t.mu_upper["Wind"]
            if 'mu_lower' in network.generators_t and "Wind" in network.generators_t.mu_lower.columns:
                wind_attrs['mu_lower'] = network.generators_t.mu_lower["Wind"]
            if 'mu_p_set' in network.generators_t and "Wind" in network.generators_t.mu_p_set.columns:
                wind_attrs['mu_p_set'] = network.generators_t.mu_p_set["Wind"]
            if 'mu_ramp_limit_up' in network.generators_t and "Wind" in network.generators_t.mu_ramp_limit_up.columns:
                wind_attrs['mu_ramp_limit_up'] = network.generators_t.mu_ramp_limit_up["Wind"]
            if 'mu_ramp_limit_down' in network.generators_t and "Wind" in network.generators_t.mu_ramp_limit_down.columns:
                wind_attrs['mu_ramp_limit_down'] = network.generators_t.mu_ramp_limit_down["Wind"]
            # Committable attributes
            if 'status' in network.generators_t and "Wind" in network.generators_t.status.columns:
                wind_attrs['status'] = network.generators_t.status["Wind"]
            if 'start_up' in network.generators_t and "Wind" in network.generators_t.start_up.columns:
                wind_attrs['start_up'] = network.generators_t.start_up["Wind"]
            if 'shut_down' in network.generators_t and "Wind" in network.generators_t.shut_down.columns:
                wind_attrs['shut_down'] = network.generators_t.shut_down["Wind"]
            attributes_dict['Wind'] = pd.DataFrame(wind_attrs)

      # For Battery StorageUnit
      if "Battery" in network.storage_units.index:
            battery_attrs = {
                'p_nom_opt': network.storage_units.at["Battery", "p_nom_opt"],
                'p_dispatch': network.storage_units_t.p_dispatch["Battery"],
                'p_store': network.storage_units_t.p_store["Battery"],
                'state_of_charge': network.storage_units_t.state_of_charge["Battery"],
            }
            # Add other attributes if available
            if 'q' in network.storage_units_t and "Battery" in network.storage_units_t.q.columns:
                battery_attrs['q'] = network.storage_units_t.q["Battery"]
            if 'spill' in network.storage_units_t and "Battery" in network.storage_units_t.spill.columns:
                battery_attrs['spill'] = network.storage_units_t.spill["Battery"]
            if 'mu_upper' in network.storage_units_t and "Battery" in network.storage_units_t.mu_upper.columns:
                battery_attrs['mu_upper'] = network.storage_units_t.mu_upper["Battery"]
            if 'mu_lower' in network.storage_units_t and "Battery" in network.storage_units_t.mu_lower.columns:
                battery_attrs['mu_lower'] = network.storage_units_t.mu_lower["Battery"]
            if 'mu_state_of_charge_set' in network.storage_units_t and "Battery" in network.storage_units_t.mu_state_of_charge_set.columns:
                battery_attrs['mu_state_of_charge_set'] = network.storage_units_t.mu_state_of_charge_set["Battery"]
            if 'mu_energy_balance' in network.storage_units_t and "Battery" in network.storage_units_t.mu_energy_balance.columns:
                battery_attrs['mu_energy_balance'] = network.storage_units_t.mu_energy_balance["Battery"]
            attributes_dict['Battery'] = pd.DataFrame(battery_attrs)

      # Print the attributes
      print("\n=== Generator and Storage Attributes ===")
      for component, df in attributes_dict.items():
            print(f"\n{component} Attributes:")
            print(df.head())  # Print first few rows for brevity
            # Or print summary
            print(f"Shape: {df.shape}")
            print(f"Columns: {list(df.columns)}")
        # Save to Excel with multiple sheets
      attributes_path = Path("generator_attributes.xlsx")
      with pd.ExcelWriter(attributes_path) as writer:
            for component, df in attributes_dict.items():
                df.to_excel(writer, sheet_name=component, index=True)
      print(f"\n✅ Generator and Storage attributes saved to '{attributes_path}'")
  except Exception as e:
    tb = traceback.format_exc()  # Get the full traceback
    traceback_logger.error(f"Exception: {str(e)}\nTraceback:\n{tb}")  # Log error with traceback
    logger.debug(f"An unexpected error occurred during optimization: {e}")