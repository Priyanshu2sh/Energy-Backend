import pypsa
import pandas as pd
from .preprocessing import preprocess_multiple_profiles
from .setup_Components import setup_network
from .createModel import optimize_network
from .run_Optimizer import analyze_network_results
import gurobipy as gp

def optimization_model(input_data, consumer_demand_path=None, hourly_demand=None, re_replacement=None, valid_combinations=None):
    
    if consumer_demand_path != None:
        demand_file = pd.read_excel(consumer_demand_path)
        demand_file = demand_file.groupby(demand_file.index // 2).mean()
        demand_file = demand_file.squeeze()
        demand_data=demand_file
    else:
        demand_file = hourly_demand.groupby(hourly_demand.index // 2).mean()
        demand_file = demand_file.squeeze()
        demand_data=demand_file
        demand_data=demand_file


    if re_replacement == None:
        DO=0.65
    else:
        DO=(re_replacement/100)

    #Curtailment
    curtailment_selling_price=3000
    sell_curtailment_percentage=0.5
    annual_curtailment_limit = 0.3
    OA_cost=1000


    results_dict = {}
    # final_dict = preprocess_multiple_profiles()
    final_dict = input_data
    for ipp in final_dict:
        # Check if any Solar, Wind, or ESS projects exist
        solar_projects = final_dict[ipp].get('Solar', {})
        wind_projects = final_dict[ipp].get('Wind', {})
        ess_projects = final_dict[ipp].get('ESS', {})

        if solar_projects and wind_projects and ess_projects:

            for solar_project in solar_projects:
                # Access Solar parameters
                solar_profile = solar_projects[solar_project]['profile']
                solar_profile = solar_profile.groupby(solar_profile.index // 2).mean()
                Solar_captialCost = solar_projects[solar_project]['capital_cost']
                Solar_marginalCost = solar_projects[solar_project]['marginal_cost']
                Solar_maxCapacity = solar_projects[solar_project]['max_capacity']
                # solar_name=solar_profile.name
                solar_name=solar_project

                # Iterate through Wind projects
                for wind_project in wind_projects:
                    # Access Wind parameters
                    wind_profile = wind_projects[wind_project]['profile']
                    wind_profile = wind_profile.groupby(wind_profile.index // 2).mean()
                    Wind_captialCost = wind_projects[wind_project]['capital_cost']
                    Wind_marginalCost = wind_projects[wind_project]['marginal_cost']
                    Wind_maxCapacity = wind_projects[wind_project]['max_capacity']
                    # wind_name=wind_profile.name
                    wind_name=wind_project

                    # Iterate through ESS projects for combinations of Solar, Wind, and Battery
                    for ess_system in ess_projects:
                        # Access Battery parameters
                        Battery_captialCost = ess_projects[ess_system]['capital_cost']
                        Battery_marginalCost = ess_projects[ess_system]['marginal_cost']
                        Battery_Eff_store = ess_projects[ess_system]['efficiency']
                        Battery_Eff_dispatch = ess_projects[ess_system]['efficiency']                 
                        DoD = ess_projects[ess_system]['DoD']
                        ess_name = ess_system

                        # Process combination of Solar, Wind, and Battery
                        print(f"IPP : {ipp} Combination of Solar: {solar_project}, Wind: {wind_project}, Battery: {ess_name}")

                        # if f'{ipp}-{solar_project}-{wind_project}-{ess_name}' in valid_combinations:
                        #     continue

                        network = setup_network(demand_data= demand_data, solar_profile= solar_profile, wind_profile =wind_profile, Solar_maxCapacity=Solar_maxCapacity, Solar_captialCost= Solar_captialCost, Solar_marginalCost= Solar_marginalCost,
                                      Wind_maxCapacity= Wind_maxCapacity, Wind_captialCost= Wind_captialCost, Wind_marginalCost = Wind_marginalCost,
                                      Battery_captialCost= Battery_captialCost, Battery_marginalCost= Battery_marginalCost, Battery_Eff_store= Battery_Eff_store, Battery_Eff_dispatch = Battery_Eff_dispatch,ess_name =ess_name, solar_name= solar_name, wind_name = wind_name)

                        m=optimize_network(network, solar_profile, wind_profile, demand_data, Solar_maxCapacity, Wind_maxCapacity,
                        Solar_captialCost, Wind_captialCost, Battery_captialCost, Solar_marginalCost, Wind_marginalCost,
                        Battery_marginalCost, sell_curtailment_percentage, curtailment_selling_price, DO, DoD, annual_curtailment_limit,ess_name)
                        analyze_network_results(network, sell_curtailment_percentage, curtailment_selling_price,solar_profile,wind_profile,results_dict,OA_cost, ess_name=ess_name, solar_name=solar_name, wind_name=wind_name, ipp_name=ipp)

        elif solar_projects and wind_projects and not ess_projects:

            for solar_project in solar_projects:
                # Access Solar parameters
                solar_profile = solar_projects[solar_project]['profile']
                solar_profile = solar_profile.groupby(solar_profile.index // 2).mean()
                Solar_captialCost = solar_projects[solar_project]['capital_cost']
                Solar_marginalCost = solar_projects[solar_project]['marginal_cost']
                Solar_maxCapacity = solar_projects[solar_project]['max_capacity']
                solar_name=solar_project

                # Iterate through Wind projects
                for wind_project in wind_projects:
                    # Access Wind parameters
                    wind_profile = wind_projects[wind_project]['profile']
                    wind_profile = wind_profile.groupby(wind_profile.index // 2).mean()
                    Wind_captialCost = wind_projects[wind_project]['capital_cost']
                    Wind_marginalCost = wind_projects[wind_project]['marginal_cost']
                    Wind_maxCapacity = wind_projects[wind_project]['max_capacity']
                    wind_name=wind_project
    


                        # Process combination of Solar, Wind, and Battery
                    print(f"IPP : {ipp} Combination of Solar: {solar_project}, Wind: {wind_project}")

                    # if f'{ipp}-{solar_project}-{wind_project}' in valid_combinations:
                    #         continue

                    network = setup_network(demand_data=demand_data, solar_profile=solar_profile, wind_profile=wind_profile,
                             Solar_maxCapacity=Solar_maxCapacity, Solar_captialCost=Solar_captialCost,
                             Solar_marginalCost=Solar_marginalCost, Wind_maxCapacity=Wind_maxCapacity,
                             Wind_captialCost=Wind_captialCost, Wind_marginalCost=Wind_marginalCost,
                             solar_name=solar_name, wind_name=wind_name)



                    m = optimize_network(network=network, solar_profile=solar_profile, wind_profile=wind_profile, demand_data=demand_data,
                                        Solar_maxCapacity=Solar_maxCapacity, Wind_maxCapacity=Wind_maxCapacity, Solar_captialCost=Solar_captialCost,
                                        Wind_captialCost=Wind_captialCost, Solar_marginalCost=Solar_marginalCost, Wind_marginalCost=Wind_marginalCost,
                                        sell_curtailment_percentage=sell_curtailment_percentage, curtailment_selling_price=curtailment_selling_price,
                                        DO=DO, annual_curtailment_limit=annual_curtailment_limit)


                    analyze_network_results(network=network, sell_curtailment_percentage=sell_curtailment_percentage,
                            curtailment_selling_price=curtailment_selling_price, solar_profile=solar_profile,
                            wind_profile=wind_profile, results_dict=results_dict, OA_cost=OA_cost, solar_name=solar_name, wind_name=wind_name, ipp_name=ipp)



        elif solar_projects and ess_projects and not wind_projects:

            for solar_project in solar_projects:
                # Access Solar parameters
                solar_profile = solar_projects[solar_project]['profile']
                solar_profile = solar_profile.groupby(solar_profile.index // 2).mean()
                Solar_captialCost = solar_projects[solar_project]['capital_cost']
                Solar_marginalCost = solar_projects[solar_project]['marginal_cost']
                Solar_maxCapacity = solar_projects[solar_project]['max_capacity']
                solar_name=solar_project

                    # Iterate through ESS projects for combinations of Solar, Wind, and Battery
                for ess_system in ess_projects:
                        # Access Battery parameters
                        Battery_captialCost = ess_projects[ess_system]['capital_cost']
                        Battery_marginalCost = ess_projects[ess_system]['marginal_cost']
                        Battery_Eff_store = ess_projects[ess_system]['efficiency']
                        Battery_Eff_dispatch = ess_projects[ess_system]['efficiency']
                        DoD = ess_projects[ess_system]['DoD']
                        ess_name = ess_system

                        # Process combination of Solar, Wind, and Battery
                        print(f"IPP : {ipp} Combination of Solar: {solar_project}, Battery: {ess_name}")

                        # if f'{ipp}-{solar_project}-{ess_name}' in valid_combinations:
                        #     continue

                        network = setup_network(demand_data=demand_data, solar_profile=solar_profile, Solar_maxCapacity=Solar_maxCapacity,
                             Solar_captialCost=Solar_captialCost, Solar_marginalCost=Solar_marginalCost,
                             Battery_captialCost=Battery_captialCost, Battery_marginalCost=Battery_marginalCost,
                             Battery_Eff_store=Battery_Eff_store, Battery_Eff_dispatch=Battery_Eff_dispatch,
                             ess_name=ess_name, solar_name=solar_name)


                        m = optimize_network(network=network, solar_profile=solar_profile, demand_data=demand_data, Solar_maxCapacity=Solar_maxCapacity,
                         Solar_captialCost=Solar_captialCost, Battery_captialCost=Battery_captialCost, Solar_marginalCost=Solar_marginalCost,
                         Battery_marginalCost=Battery_marginalCost, sell_curtailment_percentage=sell_curtailment_percentage,
                         curtailment_selling_price=curtailment_selling_price, DO=DO, DoD=DoD,
                         annual_curtailment_limit=annual_curtailment_limit, ess_name=ess_name)

                        analyze_network_results(network=network, sell_curtailment_percentage=sell_curtailment_percentage,
                            curtailment_selling_price=curtailment_selling_price, solar_profile=solar_profile,
                            results_dict=results_dict, OA_cost=OA_cost, ess_name=ess_name, solar_name=solar_name, ipp_name=ipp)



        elif wind_projects and ess_projects and not solar_projects:

            for wind_project in wind_projects:
                # Access Wind parameters
                wind_profile = wind_projects[wind_project]['profile']
                wind_profile = wind_profile.groupby(wind_profile.index // 2).mean()
                Wind_captialCost = wind_projects[wind_project]['capital_cost']
                Wind_marginalCost = wind_projects[wind_project]['marginal_cost']
                Wind_maxCapacity = wind_projects[wind_project]['max_capacity']
                wind_name=wind_project


                    # Iterate through ESS projects for combinations of Solar, Wind, and Battery
                for ess_system in ess_projects:
                        # Access Battery parameters
                        Battery_captialCost = ess_projects[ess_system]['capital_cost']
                        Battery_marginalCost = ess_projects[ess_system]['marginal_cost']
                        Battery_Eff_store = ess_projects[ess_system]['efficiency']
                        Battery_Eff_dispatch = ess_projects[ess_system]['efficiency']
                        DoD = ess_projects[ess_system]['DoD']
                        ess_name = ess_system

                        # Process combination of Solar, Wind, and Battery
                        print(f"IPP : {ipp} Combination of Wind: {wind_project}, Battery: {ess_name}")

                        # if f'{ipp}-{wind_project}-{ess_name}' in valid_combinations:
                        #     continue

                        network = setup_network(demand_data=demand_data, wind_profile=wind_profile, Wind_maxCapacity=Wind_maxCapacity,
                             Wind_captialCost=Wind_captialCost, Wind_marginalCost=Wind_marginalCost,
                             Battery_captialCost=Battery_captialCost, Battery_marginalCost=Battery_marginalCost,
                             Battery_Eff_store=Battery_Eff_store, Battery_Eff_dispatch=Battery_Eff_dispatch,
                             ess_name=ess_name, wind_name=wind_name)


                        m = optimize_network(network=network, wind_profile=wind_profile, demand_data=demand_data, Wind_maxCapacity=Wind_maxCapacity,
                         Wind_captialCost=Wind_captialCost, Battery_captialCost=Battery_captialCost, Wind_marginalCost=Wind_marginalCost,
                         Battery_marginalCost=Battery_marginalCost, sell_curtailment_percentage=sell_curtailment_percentage,
                         curtailment_selling_price=curtailment_selling_price, DO=DO, DoD=DoD,
                         annual_curtailment_limit=annual_curtailment_limit, ess_name=ess_name)

                        analyze_network_results(network=network, sell_curtailment_percentage=sell_curtailment_percentage,
                            curtailment_selling_price=curtailment_selling_price, wind_profile=wind_profile,
                            results_dict=results_dict, OA_cost=OA_cost, ess_name=ess_name, wind_name=wind_name, ipp_name=ipp)


        elif wind_projects and not solar_projects and not ess_projects:
            for wind_project in wind_projects:
                # Access Wind parameters
                wind_profile = wind_projects[wind_project]['profile']
                wind_profile = wind_profile.groupby(wind_profile.index // 2).mean()
                Wind_captialCost = wind_projects[wind_project]['capital_cost']
                Wind_marginalCost = wind_projects[wind_project]['marginal_cost']
                Wind_maxCapacity = wind_projects[wind_project]['max_capacity']
                wind_name=wind_project

                print(f"IPP : {ipp} Combination of wind: {wind_project}")

                # if f'{ipp}-{wind_project}' in valid_combinations:
                #             continue

                network = setup_network(demand_data=demand_data, wind_profile=wind_profile, Wind_maxCapacity=Wind_maxCapacity,
                             Wind_captialCost=Wind_captialCost, Wind_marginalCost=Wind_marginalCost,
                             wind_name=wind_name)


                m = optimize_network(network=network, wind_profile=wind_profile, demand_data=demand_data, Wind_maxCapacity=Wind_maxCapacity,
                         Wind_captialCost=Wind_captialCost, Wind_marginalCost=Wind_marginalCost,
                         sell_curtailment_percentage=sell_curtailment_percentage, curtailment_selling_price=curtailment_selling_price,
                         DO=DO, annual_curtailment_limit=annual_curtailment_limit)

                analyze_network_results(network=network, sell_curtailment_percentage=sell_curtailment_percentage,
                            curtailment_selling_price=curtailment_selling_price, wind_profile=wind_profile,
                            results_dict=results_dict, OA_cost=OA_cost, wind_name=wind_name, ipp_name=ipp)


        elif solar_projects and not wind_projects and not ess_projects:
            for solar_project in solar_projects:
                solar_profile = solar_projects[solar_project]['profile']
                solar_profile = solar_profile.groupby(solar_profile.index // 2).mean()
                Solar_captialCost = solar_projects[solar_project]['capital_cost']
                Solar_marginalCost = solar_projects[solar_project]['marginal_cost']
                Solar_maxCapacity = solar_projects[solar_project]['max_capacity']
                solar_name=solar_project

                print(f"IPP : {ipp} Combination of Solar: {solar_project}")

                # if f'{ipp}-{solar_project}' in valid_combinations:
                #             continue

                network = setup_network(
                  demand_data=demand_data,
                  solar_profile=solar_profile,
                  Solar_maxCapacity=Solar_maxCapacity,
                  Solar_captialCost=Solar_captialCost,
                  Solar_marginalCost=Solar_marginalCost,
                  solar_name=solar_name
                )

                m = optimize_network(network=network, solar_profile=solar_profile, demand_data=demand_data,
                         Solar_maxCapacity=Solar_maxCapacity, Solar_captialCost=Solar_captialCost,
                         Solar_marginalCost=Solar_marginalCost, sell_curtailment_percentage=sell_curtailment_percentage,
                         curtailment_selling_price=curtailment_selling_price, DO=DO,
                         annual_curtailment_limit=annual_curtailment_limit)
                
                analyze_network_results(network=network, sell_curtailment_percentage=sell_curtailment_percentage,
                            curtailment_selling_price=curtailment_selling_price, solar_profile=solar_profile,
                            results_dict=results_dict, OA_cost=OA_cost, solar_name=solar_name, ipp_name=ipp)

    
    # Convert results_dict to DataFrame for easy sorting
    if results_dict:
      
      res_df = pd.DataFrame.from_dict(results_dict, orient='index')

      # Sort by 'Per Unit Cost'
      sorted_results = res_df.sort_values(by='Per Unit Cost')
      sorted_results.to_excel("multiple_profiles_sorted_results.xlsx")
      # Convert to dictionary with index as keys
      sorted_dict = sorted_results.to_dict(orient="index")
      return sorted_dict
    else:
      print("The demand cannot be met by the IPPs")
      return "The demand cannot be met by the IPPs"

