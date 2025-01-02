
import pandas as pd
import re
def preprocess_multiple_profiles():


        solar_df=pd.read_excel(r"inputs/Profiles (1).xlsx", sheet_name="Solar")
        wind_df=pd.read_excel(r"inputs/Profiles (1).xlsx", sheet_name="Wind")


        solar_df_cleaned = solar_df.drop(solar_df.columns[0], axis=1)
        wind_df_cleaned = wind_df.drop(wind_df.columns[0], axis=1)

        solar_df_cleaned=solar_df_cleaned[2:].reset_index(drop=True)
        wind_df_cleaned=wind_df_cleaned[2:].reset_index(drop=True)

        # Set the first row as the column header for solar_df_cleaned
        solar_df_cleaned.columns = solar_df_cleaned.iloc[0]
        solar_df_cleaned = solar_df_cleaned[1:]  # Remove the first row (now the header)

        # Set the first row as the column header for wind_df_cleaned
        wind_df_cleaned.columns = wind_df_cleaned.iloc[0]
        wind_df_cleaned = wind_df_cleaned[1:]

        solar_df_cleaned = solar_df_cleaned.reset_index(drop=True)
        wind_df_cleaned = wind_df_cleaned.reset_index(drop=True)

        # Project-specific parameters
        parameters = {
            'Solar': {
                'IPP1_Project1': {
                    'max_capacity': 200,
                    'capital_cost': 0,
                    'marginal_cost': 2800,
                },
                'IPP2_Project1': {
                    'max_capacity': 130,
                    'capital_cost': 0,
                    'marginal_cost': 2700,

                },
                'IPP3_Project1': {
                    'max_capacity': 150,
                    'capital_cost': 0,
                    'marginal_cost': 2900,

                },
                'IPP1_Project2': {
                    'max_capacity': 110,
                    'capital_cost': 0,
                    'marginal_cost': 2850,

                }
            },
            'Wind': {
                'IPP1_Project1': {
                    'max_capacity': 200,
                    'capital_cost': 0,
                    'marginal_cost': 3400
                },
                'IPP2_Project1': {
                    'max_capacity': 190,
                    'capital_cost': 0,
                    'marginal_cost': 3300
                },
                'IPP3_Project1': {
                    'max_capacity': 150,
                    'capital_cost': 0,
                    'marginal_cost': 3500
                },
                'IPP1_Project2': {
                    'max_capacity': 180,
                    'capital_cost': 0,
                    'marginal_cost': 3500
                }
            },
            'ESS': {
                    'IPP1_ESS1': {
                        'capital_cost': 18000000,
                        'marginal_cost': 60,
                        'efficiency': 0.95,
                        'DoD': 0.80
                        },
                    'IPP2_ESS1': {
                        'capital_cost': 18000000,
                        'marginal_cost': 62,
                        'efficiency': 0.95,
                        'DoD': 0.80
                    },
                    'IPP3_ESS1': {
                        'capital_cost': 18000000,
                        'marginal_cost': 55,
                        'efficiency': 0.95,
                        'DoD': 0.80
                    },
                    'IPP1_ESS2': {
                        'capital_cost': 18000000,
                        'marginal_cost': 50,
                        'efficiency': 0.95,
                        'DoD': 0.80
                    },
                    'IPP3_ESS2': {
                        'capital_cost': 18000000,
                        'marginal_cost': 52,
                        'efficiency': 0.95,
                        'DoD': 0.80
                    }

                    
            }
        }


        #Create Dictionary
        def extract_ipp_project(column_name):
            match = re.match(r'(\w+)_(IPP\d+)_Project(\d+)', column_name)
            if match:
                return match.groups()  # Returns ("Technology", "IPP", "Project")
            return None

        def create_profile_dict(df, technology, parameters):
            profile_dict = {}
            for column in df.columns:
                parsed = extract_ipp_project(column)
                if parsed:
                    tech, ipp, project = parsed
                    project_key = f"{ipp}_Project{project}"
                    if ipp not in profile_dict:
                        profile_dict[ipp] = {"Solar": {}, "Wind": {},"ESS": {}}

                    profile = df[column].fillna(0).reset_index(drop=True)  # Series of hourly data
                    project_params = parameters[technology].get(project_key, {})
                    project_dict = {
                        "profile": profile,
                        "max_capacity": project_params.get("max_capacity"),
                        "capital_cost": project_params.get("capital_cost"),
                        "marginal_cost": project_params.get("marginal_cost")
                    }

                    if technology == "Solar" and "ESS" in project_params:
                        project_dict["ESS"] = project_params["ESS"]

                    profile_dict[ipp][technology][f"{technology}_{project}"] = project_dict

            return profile_dict
        
        def create_profile_dict_ess(technology,parameters):
            ess_dict={}
            for ess_projects,details in parameters['ESS'].items():
                match = re.match(r'(IPP\d+)_ESS(\d+)', ess_projects)
                ipp, project_no = match.groups()     
                if ipp not in ess_dict:
                  ess_dict[ipp] = {"ESS": {}}           
                ess_dict[ipp][technology][f"{technology}_{project_no}"] = details

            return ess_dict

        ess_params = create_profile_dict_ess("ESS",parameters)

        # Create dictionaries for Solar and Wind
        solar_profiles = create_profile_dict(solar_df_cleaned, "Solar", parameters)
        wind_profiles = create_profile_dict(wind_df_cleaned, "Wind", parameters)

        # Merge Solar and Wind dictionaries
        final_dict = solar_profiles
        for ipp, data in wind_profiles.items():
            if ipp in final_dict:
                final_dict[ipp]["Wind"].update(data["Wind"])
            else:
                final_dict[ipp] = data

        for ipp, data in ess_params.items():
            if ipp in final_dict:
                final_dict[ipp]["ESS"].update(data["ESS"])
            else:
                final_dict[ipp] = data

        #changes for testing
        # if "IPP2" in final_dict and "Wind" in final_dict["IPP2"]:
        #     del final_dict["IPP2"]["Wind"]

        # if "IPP1" in final_dict and "Solar" in final_dict["IPP1"] and "ESS" in final_dict["IPP1"]:
        #     del final_dict["IPP1"]["Wind"]
        #     del final_dict["IPP1"]["ESS"]

        # if "IPP3" in final_dict and "Solar" in final_dict["IPP3"]:
        #     del final_dict["IPP3"]["Solar"]
        
        return final_dict


# import pandas as pd
# import re

# def preprocess_multiple_profiles():
#     solar_df = pd.read_excel(r"inputs/Profiles (1).xlsx", sheet_name="Solar")
#     wind_df = pd.read_excel(r"inputs/Profiles (1).xlsx", sheet_name="Wind")

#     solar_df_cleaned = solar_df.drop(solar_df.columns[0], axis=1)
#     wind_df_cleaned = wind_df.drop(wind_df.columns[0], axis=1)

#     solar_df_cleaned = solar_df_cleaned[2:].reset_index(drop=True)
#     wind_df_cleaned = wind_df_cleaned[2:].reset_index(drop=True)

#     # Set headers
#     solar_df_cleaned.columns = solar_df_cleaned.iloc[0]
#     solar_df_cleaned = solar_df_cleaned[1:].reset_index(drop=True)
#     wind_df_cleaned.columns = wind_df_cleaned.iloc[0]
#     wind_df_cleaned = wind_df_cleaned[1:].reset_index(drop=True)

#     parameters = {
#         'Solar': {
#             'IPP1_Project1': {'max_capacity': 200, 'capital_cost': 0, 'marginal_cost': 2800},
#             'IPP2_Project1': {'max_capacity': 130, 'capital_cost': 0, 'marginal_cost': 2700},
#             'IPP3_Project1': {'max_capacity': 150, 'capital_cost': 0, 'marginal_cost': 2900},
#             'IPP1_Project2': {'max_capacity': 110, 'capital_cost': 0, 'marginal_cost': 2850},
#         },
#         'Wind': {
#             'IPP1_Project1': {'max_capacity': 200, 'capital_cost': 0, 'marginal_cost': 3400},
#             'IPP2_Project1': {'max_capacity': 190, 'capital_cost': 0, 'marginal_cost': 3300},
#             'IPP3_Project1': {'max_capacity': 150, 'capital_cost': 0, 'marginal_cost': 3500},
#             'IPP1_Project2': {'max_capacity': 180, 'capital_cost': 0, 'marginal_cost': 3500},
#         },
#         'ESS': {
#             'IPP1_ESS1': {'capital_cost': 18000000, 'marginal_cost': 60, 'efficiency': 0.95, 'DoD': 0.80},
#             'IPP2_ESS1': {'capital_cost': 18000000, 'marginal_cost': 62, 'efficiency': 0.95, 'DoD': 0.80},
#             'IPP3_ESS1': {'capital_cost': 18000000, 'marginal_cost': 55, 'efficiency': 0.95, 'DoD': 0.80},
#             'IPP1_ESS2': {'capital_cost': 18000000, 'marginal_cost': 50, 'efficiency': 0.95, 'DoD': 0.80},
#             'IPP3_ESS2': {'capital_cost': 18000000, 'marginal_cost': 52, 'efficiency': 0.95, 'DoD': 0.80},
#         }
#     }

#     def extract_ipp_project(column_name):
#         match = re.match(r'(\w+)_(IPP\d+)_Project(\d+)', column_name)
#         if match:
#             return match.groups()
#         return None

#     def create_profile_dict(df, technology, parameters):
#         profile_dict = {}
#         for column in df.columns:
#             parsed = extract_ipp_project(column)
#             if parsed:
#                 _, ipp, project = parsed
#                 project_key = f"{ipp}_Project{project}"
#                 if ipp not in profile_dict:
#                     profile_dict[ipp] = {"Solar": {}, "Wind": {}, "ESS": {}}

#                 profile = df[column].fillna(0).reset_index(drop=True)
#                 project_params = parameters[technology].get(project_key, {})
#                 profile_dict[ipp][technology][f"{technology}_{project}"] = {
#                     "profile": profile,
#                     **project_params,
#                 }
#         return profile_dict

#     def create_profile_dict_ess(parameters):
#         ess_dict = {}
#         for ess_projects, details in parameters['ESS'].items():
#             match = re.match(r'(IPP\d+)_ESS(\d+)', ess_projects)
#             if match:
#                 ipp, project_no = match.groups()
#                 if ipp not in ess_dict:
#                     ess_dict[ipp] = {"ESS": {}}
#                 ess_dict[ipp]["ESS"][f"ESS_{project_no}"] = details
#         return ess_dict

#     ess_params = create_profile_dict_ess(parameters)
#     solar_profiles = create_profile_dict(solar_df_cleaned, "Solar", parameters)
#     wind_profiles = create_profile_dict(wind_df_cleaned, "Wind", parameters)

#     final_dict = solar_profiles
#     for ipp, data in wind_profiles.items():
#         if ipp in final_dict:
#             final_dict[ipp]["Wind"].update(data["Wind"])
#         else:
#             final_dict[ipp] = data
#     for ipp, data in ess_params.items():
#         if ipp in final_dict:
#             final_dict[ipp]["ESS"].update(data["ESS"])
#         else:
#             final_dict[ipp] = data

#     return final_dict
