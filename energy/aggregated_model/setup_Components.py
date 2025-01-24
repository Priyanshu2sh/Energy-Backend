import pypsa
def setup_network(demand_data=None, solar_profile=None, wind_profile=None, Solar_maxCapacity=None, Solar_captialCost=None, Solar_marginalCost=None,
                  Wind_maxCapacity=None, Wind_captialCost=None, Wind_marginalCost=None,
                  Battery_captialCost = None, Battery_marginalCost= None,Battery_Eff_store=None,Battery_Eff_dispatch=None,snapshots=None,ess_name=None,solar_name=None,wind_name=None):
    """
    Function to initialize and set up the PyPSA network with demand, solar, wind, battery storage,
    and unmet demand generator.

    Parameters:
    - demand_data (pd.Series): Time-series data for demand (in MW).
    - solar_profile (pd.Series): Solar generation profile (per unit, 0 to 1).
    - wind_profile (pd.Series): Wind generation profile (per unit, 0 to 1).
    - Solar_maxCapacity (float): Maximum capacity for solar generators (MW).
    - Solar_captialCost (float): Capital cost for solar generators (INR/MW).
    - Solar_marginalCost (float): Marginal cost for solar generation (INR/MWh).
    - Wind_maxCapacity (float): Maximum capacity for wind generators (MW).
    - Wind_captialCost (float): Capital cost for wind generators (INR/MW).
    - Wind_marginalCost (float): Marginal cost for wind generation (INR/MWh).
    - Battery_captialCost (float): Capital cost for battery storage (INR/MW).
    - Battery_marginalCost (float): Marginal cost for battery storage (INR/MWh).
    - snapshots (pd.Index, optional): Custom index for snapshots (default is None, which uses solar profile's index).

    Returns:
    - network (pypsa.Network): Initialized and configured PyPSA network.
    """

    # Initialize the PyPSA network
    network = pypsa.Network()
    if demand_data is not None:
      snapshots = demand_data.index
      network.set_snapshots(snapshots)


    # Add bus to the network
    network.add("Bus", "ElectricityBus", carrier="AC")



    # Add demand as a load on the bus
    network.add("Load",
                "ElectricityDemand",
                bus="ElectricityBus",
                p_set=demand_data.squeeze())  # squeeze() if demand_data is a single-column DataFrame

    # Add solar generator with profile
    if solar_name is not None:
            network.add("Generator",
                        "Solar",
                        bus="ElectricityBus",
                        p_nom_extendable=True,  # Allow optimization of solar capacity
                        p_nom_max=Solar_maxCapacity,
                        capital_cost=Solar_captialCost,
                        marginal_cost=Solar_marginalCost,
                        p_max_pu=solar_profile.squeeze())  # Using the solar profile as per-unit scaling

    # Add wind generator with profile
    if wind_name is not None:
            network.add("Generator",
                        "Wind",
                        bus="ElectricityBus",
                        p_nom_extendable=True,
                        p_nom_max=Wind_maxCapacity,
                        capital_cost=Wind_captialCost,
                        marginal_cost=Wind_marginalCost,
                        p_max_pu=wind_profile.squeeze())  # Wind profile

    # Add battery storage with profile
    if ess_name is not None:
            network.add("StorageUnit",
                        "Battery",
                        bus="ElectricityBus",
                        p_nom_extendable=True,             # Allow optimization of storage capacity
                        capital_cost=Battery_captialCost,              # Capital cost in INR (₹60 lakh/MW)
                        marginal_cost=Battery_marginalCost,                   # Operational cost per MWh (e.g., degradation cost)
                        efficiency_store=Battery_Eff_store,              # Charging efficiency
                        efficiency_dispatch=Battery_Eff_dispatch,           # Discharging efficiency
                        # DoD=0.2,           # Minimum state of charge (1 - DoD), for DoD = 0.8
            )

    # Add generator for unmet demand
    network.add("Generator", "Unmet_Demand",
                bus="ElectricityBus",
                p_nom=1e6,          # Large capacity to ensure it can cover all unmet demand if needed
                marginal_cost=0,  # High marginal cost to use only when absolutely necessary
                carrier="Unmet_Demand")

    return network