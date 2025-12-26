import logging
from linopy import LinearExpression
logger = logging.getLogger('debug_logger')  # Use the new debug logger

def optimize_network(network=None, solar_profile=None, wind_profile=None, demand_data=None,
                     Solar_maxCapacity=None, Wind_maxCapacity=None, Solar_captialCost=None,
                     Wind_captialCost=None, Battery_captialCost=None, Solar_marginalCost=None,
                     Wind_marginalCost=None, Battery_marginalCost=None, sell_curtailment_percentage=None,
                     curtailment_selling_price=None, DO=None, DoD=None, annual_curtailment_limit=None,
                     ess_name=None,  peak_target=None, peak_hours=None, max_hours=None, transmission_capacity=None,
                     monthly_availability=None):

    solar_present = solar_profile is not None and not solar_profile.empty
    wind_present = wind_profile is not None and not wind_profile.empty

    m = network.optimize.create_model()
    if solar_present:
        m.add_variables(
          lower=0,
          dims=["snapshot"],
          coords={"snapshot": network.snapshots},
          name="Solar_curtailment"
      )
        def solar_curtailment_calculation(s):
            solar_generation = m.variables["Generator-p_nom"].loc["Solar"] * network.generators_t.p_max_pu["Solar"]
            # logger.debug(f"Solar  with generator p_nom: {solar_generation}")
            network_g = network.generators_t.p_max_pu["Solar"]
            # logger.debug(f"network generation:------------")
            # logger.debug(f"network generation: {network_g}")
            solar_allocation = m.variables["Generator-p"].loc[s, "Solar"]
            constraint_expr = m.variables['Solar_curtailment'] == (solar_generation - solar_allocation)
            m.add_constraints(constraint_expr, name="solar_curtailment_calculation_constraint")

        solar_curtailment_calculation(network.snapshots)

    if wind_present:
        m.add_variables(
          lower=0,
          dims=["snapshot"],
          coords={"snapshot": network.snapshots},
          name="Wind_curtailment"
      )
        def wind_curtailment_calculation(s):
            wind_generation = m.variables["Generator-p_nom"].loc["Wind"] * network.generators_t.p_max_pu["Wind"]
            # logger.debug(f"Wind generation p nom: {wind_generation}")

            wind_generation_1 = network.generators_t.p_max_pu["Wind"]
            # logger.debug(f"network generation:------------")
            # logger.debug(f"network generation: {wind_generation_1}")
            wind_allocation = m.variables["Generator-p"].loc[s, "Wind"]
            constraint_expr = m.variables['Wind_curtailment'] == (wind_generation - wind_allocation)
            m.add_constraints(constraint_expr, name="wind_curtailment_calculation_constraint")

        wind_curtailment_calculation(network.snapshots)

    m.add_variables(
        lower=0,
        dims=["snapshot"],
        coords={"snapshot": network.snapshots},
        name="Final_snapshot_curtailment"
    )

    # Update the objective function to include only variable terms
    m.objective += m.variables['Final_snapshot_curtailment'].sum()


    def add_demand_offset_constraint():
        total_demand = network.loads_t.p_set.sum().sum()
        constraint_expr = (m.variables["Generator-p"].loc[:, 'Unmet_Demand']).sum() <= (1-DO) * total_demand
        m.add_constraints(constraint_expr, name="demand_offset_constraint")
    
    def add_peak_hour_constraint(peak_target=None, peak_hours=None):
        if peak_target is None or peak_hours is None:
            return  # skip if not provided

        # Mask for snapshots falling in user-defined peak hours
        peak_mask = network.snapshots.to_series().dt.hour.isin(peak_hours)

        total_peak_demand = network.loads_t.p_set.loc[peak_mask, "ElectricityDemand"].sum()
        peak_indices = network.snapshots[peak_mask]
        unmet_peak = m.variables["Generator-p"].loc[peak_indices, 'Unmet_Demand'].sum()

        # Add stronger penalty for unmet demand during peak hours
        peak_penalty = 500  # Reduced from 1000 to allow more flexibility
        penalty_expr = unmet_peak * peak_penalty
        m.objective += penalty_expr

        # Add cost minimization objective
        # if solar_present:
        #     solar_cost = m.variables["Generator-p_nom"].loc['Solar'] * Solar_captialCost
        #     m.objective += solar_cost * 0.2  # Weight factor to balance cost vs performance

        # if ess_name is not None:
        #     battery_cost = m.variables["StorageUnit-p_nom"].loc['Battery'] * Battery_captialCost
        #     m.objective += battery_cost * 0.2  # Weight factor for battery cost

        # Ensure unmet demand <= (1 - peak_target) * demand during peak hours only
        constraint_expr = unmet_peak <= (1 - peak_target) * total_peak_demand
        m.add_constraints(constraint_expr, name="peak_hour_demand_constraint")

    add_demand_offset_constraint()
    add_peak_hour_constraint(peak_target=peak_target, peak_hours=peak_hours)

    def add_monthly_availability_constraints(monthly_targets):
        """Enforce that for each calendar month the model meets at least the
        user-provided percentage of demand. monthly_targets should be an iterable
        with 12 values (one per month), or 1 value to replicate across all months.
        Values can be in 0-1 or 0-100 format.
        """
        if not monthly_targets:
            return

        # Convert to list and validate length
        try:
            targets = list(monthly_targets)
        except Exception:
            logger.warning("monthly_availability provided but could not be parsed; skipping monthly constraints")
            return

        # Handle single value case: replicate across all 12 months
        if len(targets) == 1:
            logger.info(f"Single monthly availability value provided ({targets[0]}). Applying to all 12 months.")
            targets = targets * 12
        elif len(targets) != 12:
            logger.warning("monthly_availability must contain 12 values (Jan..Dec) or 1 value for all months; skipping monthly constraints")
            return

        # Normalise values to [0,1] (allow users to input percentages 0-100)
        norm_targets = []
        for t in targets:
            try:
                tt = float(t)
            except Exception:
                logger.warning(f"Invalid monthly availability value '{t}' - treating as 0")
                tt = 0.0
            if tt > 1.0:
                tt = tt / 100.0
            norm_targets.append(max(0.0, min(1.0, tt)))

        # Group snapshots by calendar month and add constraint per month
        snaps_series = network.snapshots.to_series()
        for month_idx, month_target in enumerate(norm_targets, start=1):
            month_mask = snaps_series.dt.month == month_idx
            if not month_mask.any():
                # No snapshots for this calendar month in the dataset
                continue
            month_snaps = network.snapshots[month_mask.values]

            # total demand in that month (sum across all load entries if present)
            try:
                # Typical setup uses a single load called 'ElectricityDemand'
                total_month_demand = network.loads_t.p_set.loc[month_snaps].sum().sum()
            except Exception:
                # Fallback: sum all entries
                total_month_demand = network.loads_t.p_set.loc[month_snaps].sum().sum()

            # Unmet demand for snapshots in this month
            unmet_month = (m.variables["Generator-p"].loc[month_snaps, 'Unmet_Demand']).sum()

            # Constrain unmet demand to be <= (1 - month_target) * total_month_demand
            constraint_expr = unmet_month <= (1.0 - month_target) * total_month_demand
            m.add_constraints(constraint_expr, name=f"monthly_availability_constraint_month_{month_idx}")

    # Add monthly availability constraints if provided
    add_monthly_availability_constraints(monthly_availability)

    # Step 4: Add State of Charge (SOC) and DoD constraint for storage
    if ess_name is not None:
        def add_SOC_DoD_constraint():
            snapshots_except_first = network.snapshots[1:].to_list()
            constraint_expr = m.variables["StorageUnit-state_of_charge"].loc[snapshots_except_first, 'Battery'] >= (1-DoD) * m.variables["StorageUnit-p_nom"]
            m.add_constraints(constraint_expr, name="SOC_DoD_constraint")

        add_SOC_DoD_constraint()

    # Add battery energy capacity constraint
    # if ess_name is not None and Battery_max_energy_capacity is not None:
    #     soc   = m.variables["StorageUnit-state_of_charge"].loc[:, "Battery"]
    #     p_nom = m.variables["StorageUnit-p_nom"].loc["Battery"]
    #     m.add_constraints(soc <= p_nom * float(Battery_max_energy_capacity),
    #                     name="battery_energy_capacity_constraint")
    #     # Add DoD constraint (optional but recommended)
    #     if DoD is not None:
    #         snapshots_except_first = network.snapshots[1:].to_list()
    #         constraint_expr = (
    #             m.variables["StorageUnit-state_of_charge"].loc[snapshots_except_first, 'Battery'] 
    #             >= (1 - DoD) * m.variables["StorageUnit-p_nom"].loc['Battery'] * Battery_max_energy_capacity
    #         )
    #         m.add_constraints(constraint_expr, name="battery_DoD_constraint")


    if solar_present and  wind_present:
        # Step 7: Final curtailment cost calculation
        def final_curtailment_cost_calculation(s):
            curtailment_marginal = (m.variables['Solar_curtailment'] * network.generators.at["Solar", "marginal_cost"]) + \
                                  (m.variables['Wind_curtailment'] * network.generators.at["Wind", "marginal_cost"])
            sell_curtailment = (sell_curtailment_percentage * (m.variables['Solar_curtailment'] + m.variables['Wind_curtailment'])) * curtailment_selling_price
            constraint_expr = m.variables['Final_snapshot_curtailment'] == (curtailment_marginal - sell_curtailment)
            m.add_constraints(constraint_expr, name="final_curtailment_cost_calculation_constraint")

        final_curtailment_cost_calculation(network.snapshots)

            # Step 8: Add annual curtailment upper limit constraint
        def add_annual_curtailment_upper_limit_constraint():
            annual_solar_curt = m.variables['Solar_curtailment'].sum()
            annual_wind_curt = m.variables['Wind_curtailment'].sum()
            annual_gen = (m.variables["Generator-p_nom"].loc["Solar"] * network.generators_t.p_max_pu["Solar"] +
                          m.variables["Generator-p_nom"].loc["Wind"] * network.generators_t.p_max_pu["Wind"]).sum()
            # logger.debug(f"Annual solar curtailment: {annual_solar_curt}")
            # logger.debug(f"Annual wind curtailment: {annual_wind_curt}")
            # logger.debug(f"Annual generation: {annual_gen}")

            annual_gen_1 = (network.generators_t.p_max_pu["Solar"] + network.generators_t.p_max_pu["Wind"]).sum()
            # logger.debug(f"Annual generation solar-----: {annual_gen_1}")

            annual_curt = annual_solar_curt + annual_wind_curt
            constraint_expr = annual_curt <= annual_curtailment_limit * annual_gen
            # logger.debug(f"Annual curtailment: {annual_curt}")
            # logger.debug(f"Annual curtailment limit: {annual_curtailment_limit * annual_gen}")
            m.add_constraints(constraint_expr, name="annual_curtailment_upper_limit_constraint")

        add_annual_curtailment_upper_limit_constraint()

    elif solar_present and not wind_present:
      def final_curtailment_cost_calculation(s):
            curtailment_marginal = (m.variables['Solar_curtailment'] * network.generators.at["Solar", "marginal_cost"])
            sell_curtailment = (sell_curtailment_percentage * (m.variables['Solar_curtailment'])) * curtailment_selling_price
            constraint_expr = m.variables['Final_snapshot_curtailment'] == (curtailment_marginal - sell_curtailment)
            m.add_constraints(constraint_expr, name="final_curtailment_cost_calculation_constraint")

      final_curtailment_cost_calculation(network.snapshots)

            # Step 8: Add annual curtailment upper limit constraint
      def add_annual_curtailment_upper_limit_constraint():
          annual_solar_curt = m.variables['Solar_curtailment'].sum()
          annual_gen = (m.variables["Generator-p_nom"].loc["Solar"] * network.generators_t.p_max_pu["Solar"]).sum()

        #   logger.debug(f"Annual solar curtailment: {annual_solar_curt}")
        #   logger.debug(f"Annual generation for only solar with Generator-p_nom : {annual_gen}")

          annual_gen_111 = (network.generators_t.p_max_pu["Solar"]).sum()
        #   logger.debug(f"Annual generation only solar : {annual_gen_111}")

          annual_curt = annual_solar_curt
          constraint_expr = annual_curt <= annual_curtailment_limit * annual_gen
          m.add_constraints(constraint_expr, name="annual_curtailment_upper_limit_constraint")

      add_annual_curtailment_upper_limit_constraint()

    elif wind_present and not solar_present:
      def final_curtailment_cost_calculation(s):
            curtailment_marginal = (m.variables['Wind_curtailment'] * network.generators.at["Wind", "marginal_cost"])
            sell_curtailment = (sell_curtailment_percentage * (m.variables['Wind_curtailment'])) * curtailment_selling_price
            constraint_expr = m.variables['Final_snapshot_curtailment'] == (curtailment_marginal - sell_curtailment)
            m.add_constraints(constraint_expr, name="final_curtailment_cost_calculation_constraint")

      final_curtailment_cost_calculation(network.snapshots)

            # Step 8: Add annual curtailment upper limit constraint
      def add_annual_curtailment_upper_limit_constraint():
          annual_wind_curt = m.variables['Wind_curtailment'].sum()
          annual_gen = (m.variables["Generator-p_nom"].loc["Wind"] * network.generators_t.p_max_pu["Wind"]).sum()
        #   logger.debug(f"Annual wind curtailment: {annual_wind_curt}")
        #   logger.debug(f"Annual generation for only wind with Generator-p_nom : {annual_gen}")

          annual_curt = annual_wind_curt
          constraint_expr = annual_curt <= annual_curtailment_limit * annual_gen
          m.add_constraints(constraint_expr, name="annual_curtailment_upper_limit_constraint")

      add_annual_curtailment_upper_limit_constraint()
    # logger.debug("Model optimization completed successfull {m.constraints}")
    # logger.debug("Model optimization completed successfull {m.objective}")
    # logger.debug("Model optimization completed successfull {m.variables}")


    if transmission_capacity is not None:
        total_allocated = 0  # Initialize as scalar; linopy will promote to LinearExpression
        if solar_present:
            total_allocated += m.variables["Generator-p"].loc[:, "Solar"]
        if wind_present:
            total_allocated += m.variables["Generator-p"].loc[:, "Wind"]
        if ess_name is not None:
            total_allocated += m.variables["StorageUnit-p_dispatch"].loc[:, "Battery"] - m.variables["StorageUnit-p_store"].loc[:, "Battery"]
        m.add_constraints(total_allocated <= transmission_capacity, name="transmission_capacity_constraint")


    # Add battery charging constraint (after all variables are defined)
    if ess_name is not None:
        battery_store = m.variables["StorageUnit-p_store"].loc[:, "Battery"]
        real_gen = None
        if solar_present and wind_present:
            solar_gen = m.variables["Generator-p"].loc[:, "Solar"]
            wind_gen = m.variables["Generator-p"].loc[:, "Wind"]
            real_gen = solar_gen + wind_gen
        elif solar_present:
            real_gen = m.variables["Generator-p"].loc[:, "Solar"]
        elif wind_present:
            real_gen = m.variables["Generator-p"].loc[:, "Wind"]
        if real_gen is not None:
            m.add_constraints(battery_store <= real_gen, name="battery_charge_from_real_gen_only")
            m.add_constraints(battery_store >= 0, name="battery_store_nonnegative")

    return m