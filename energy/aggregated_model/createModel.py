import logging
from linopy import LinearExpression
logger = logging.getLogger('debug_logger')  # Use the new debug logger

def optimize_network(network=None, solar_profile=None, wind_profile=None, demand_data=None,
                     Solar_maxCapacity=None, Wind_maxCapacity=None, Solar_captialCost=None,
                     Wind_captialCost=None, Battery_captialCost=None, Solar_marginalCost=None,
                     Wind_marginalCost=None, Battery_marginalCost=None, sell_curtailment_percentage=None,
                     curtailment_selling_price=None, DO=None, DoD=None, annual_curtailment_limit=None,
                     ess_name=None):

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

    m.objective += m.variables['Final_snapshot_curtailment'].sum()

    # Step 3: Add demand offset constraint
    def add_demand_offset_constraint():
        total_demand = network.loads_t.p_set.sum().sum()
        constraint_expr = (m.variables["Generator-p"].loc[:, 'Unmet_Demand']).sum() <= (1-DO) * total_demand
        m.add_constraints(constraint_expr, name="demand_offset_constraint")

    add_demand_offset_constraint()

    # Step 4: Add State of Charge (SOC) and DoD constraint for storage
    if ess_name is not None:
        def add_SOC_DoD_constraint():
            snapshots_except_first = network.snapshots[1:].to_list()
            constraint_expr = m.variables["StorageUnit-state_of_charge"].loc[snapshots_except_first, 'Battery'] >= (1-DoD) * m.variables["StorageUnit-p_nom"]
            m.add_constraints(constraint_expr, name="SOC_DoD_constraint")

        add_SOC_DoD_constraint()

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

    return m
