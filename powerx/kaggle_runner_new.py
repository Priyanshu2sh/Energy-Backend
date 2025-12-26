from datetime import datetime
import os
os.environ["KAGGLE_USERNAME"] = "prushaltech13"
os.environ["KAGGLE_KEY"] = "e1f17168a76939af4f94a780630c61d7"
import subprocess
import shutil
import time

# Config
current_dir = os.path.dirname(os.path.abspath(__file__))
input_data = os.path.join(current_dir, "input_data")
# NOTEBOOK_PATH = os.path.join(current_dir, "optimize_model.ipynb")
DATASET_DIR = input_data              # your local exports folder (input data)
OUTPUT_DIR = "outputs"                # where outputs will be saved

# Add your notebooks here:
NOTEBOOKS = [
    # os.path.join(current_dir, "Next_day_MCP_final.ipynb"),
    # os.path.join(current_dir, "Next_day_MCV_final.ipynb"),
    os.path.join(current_dir, "Month_ahead.ipynb")
]

# Kaggle identifiers
USERNAME = "prushaltech13"
DATASET_SLUG = f"{USERNAME}/my-input-dataset"

def upload_dataset(): 
    if not os.path.exists(DATASET_DIR): 
        raise FileNotFoundError(f"{DATASET_DIR} folder not found!") 

    subprocess.run( 
        ["kaggle", "datasets", "version", "-p", DATASET_DIR, "-m", "new version"], check=True 
    )

    # File name with today's date
    today_str = datetime.now().strftime("%Y-%m-%d")
    file_name = f"{today_str}_input_data.csv"

    # Path to input_data folder (current directory)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    input_data_dir = os.path.join(current_dir, "input_data")
    file_path = os.path.join(input_data_dir, file_name)

    # Delete the file if it exists
    if os.path.exists(file_path):
        os.remove(file_path)
        print(f"{file_name} deleted successfully from input_data folder")
    else:
        print(f"{file_name} not found in input_data folder")


# 2. Push notebook
def upload_notebook(nb_path):
    nb_name = os.path.basename(nb_path)

    safe_name = nb_name.replace('.ipynb', '').lower().replace(' ', '-')
    kernel_slug = f"{USERNAME}/{safe_name}"
    kernel_slug = kernel_slug.replace('_', '-')

    work_dir = f"notebook_dir_{safe_name}"
    os.makedirs(work_dir, exist_ok=True)
    shutil.copy(nb_path, work_dir)

    kernel_metadata = f"""{{
  "id": "{kernel_slug}",
  "title": "{safe_name}",
  "code_file": "{nb_name}",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": true,
  "enable_gpu": true,
  "dataset_sources": ["{DATASET_SLUG}"]
}}"""
    with open(f"{work_dir}/kernel-metadata.json", "w") as f:
        f.write(kernel_metadata)

    subprocess.run(["kaggle", "kernels", "push", "-p", work_dir], check=True)

    return kernel_slug

def run_notebook(kernel_slug, nb_name):
    print("⏳ Waiting for Kaggle to finish execution...")

    # Poll until finished
    while True:
        status = subprocess.run(
            ["kaggle", "kernels", "status", kernel_slug],
            capture_output=True,
            text=True
        )

        text = status.stdout.lower()

        if "complete" in text:
            print(f"✅ Notebook {nb_name} finished successfully.")
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            output_path = os.path.join(OUTPUT_DIR, nb_name.replace(".ipynb", ""))
            os.makedirs(output_path, exist_ok=True)
            subprocess.run(
                ["kaggle", "kernels", "output", kernel_slug, "-p", output_path],
                check=True
            )
            return

        if "error" in text or "failed" in text or status.returncode != 0:
            print(f"❌ Kernel failed for {nb_name}. Fetching logs...")
            break

        time.sleep(20)

    # Download outputs/logs
    log_dir = os.path.join("outputs", "logs", kernel_slug.replace("/", "_"))
    os.makedirs(log_dir, exist_ok=True)

    subprocess.run(
        ["kaggle", "kernels", "output", kernel_slug, "-p", log_dir],
        check=False
    )

    print(f"📂 Logs downloaded to: {log_dir}")

    raise RuntimeError(f"Kernel failed for {nb_name}. See logs in {log_dir}")


# 3. Poll Kaggle until notebook execution finishes, then download outputs
# def run_notebook(kernel_slug, nb_name):
#     print('ssssssssssssssssssssssssssssssssssssssssss')
#     print(kernel_slug)
#     print('ssssssssssssssssssssssssssssssssssssssssss')
#     print("⏳ Waiting for Kaggle to finish execution...")
#     for _ in range(40):  # ~15 mins max wait
#         status = subprocess.run(
#             ["kaggle", "kernels", "status", kernel_slug],
#             capture_output=True,
#             text=True
#         )
#         print(status.stdout.strip())
#         print('--------------------------------')
#         print(status)
#         print('--------------------------------')

#         if "complete" in status.stdout.lower():
#             print(f"✅ Execution finished for {nb_name}, downloading outputs...")
#             os.makedirs(OUTPUT_DIR, exist_ok=True)
#             output_path = os.path.join(OUTPUT_DIR, nb_name.replace(".ipynb", ""))
#             os.makedirs(output_path, exist_ok=True)
#             subprocess.run(
#                 ["kaggle", "kernels", "output", kernel_slug, "-p", output_path],
#                 check=True
#             )
#             return

#         if "error" in status.stdout.lower():
#             # -------- NEW LOG DOWNLOAD BLOCK --------
#             print(f"❌ Kernel failed for {nb_name}. Fetching logs...")

#             # -------- FAIL AFTER LOG HANDLING --------
#             raise RuntimeError(f"❌ Kernel failed for {nb_name}. Check logs.")


#         time.sleep(30)

#     raise TimeoutError("⚠️ Kernel did not finish in time.")

# Master execution pipeline:
def run_pipeline():
    print("\n--- Uploading Dataset ---")
    upload_dataset()

    for nb in NOTEBOOKS:
        print(f"\n--- Uploading Notebook: {os.path.basename(nb)} ---")
        kernel = upload_notebook(nb)

        print(f"--- Running Notebook: {os.path.basename(nb)} ---")
        run_notebook(kernel, os.path.basename(nb))
