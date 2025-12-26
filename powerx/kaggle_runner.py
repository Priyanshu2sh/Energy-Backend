import os
import subprocess
import shutil
import time

# Config
current_dir = os.path.dirname(os.path.abspath(__file__))
input_data = os.path.join(current_dir, "input_data")
NOTEBOOK_PATH = os.path.join(current_dir, "optimize_model.ipynb")
DATASET_DIR = input_data              # your local exports folder (input data)
OUTPUT_DIR = "outputs"                # where outputs will be saved

# Kaggle identifiers
USERNAME = "prushaltech13"
DATASET_SLUG = f"{USERNAME}/my-input-dataset"
KERNEL_SLUG = f"{USERNAME}/my-gpu-notebook"

def upload_dataset(): 
    if not os.path.exists(DATASET_DIR): 
        raise FileNotFoundError(f"{DATASET_DIR} folder not found!") 

    subprocess.run( 
        ["kaggle", "datasets", "version", "-p", DATASET_DIR, "-m", "new version"], check=True 
    )


# 2. Push notebook
def upload_notebook():
    os.makedirs("notebook_dir", exist_ok=True)
    shutil.copy(NOTEBOOK_PATH, "notebook_dir/")

    kernel_metadata = f"""
{{
  "id": "{KERNEL_SLUG}",
  "title": "My GPU Notebook",
  "code_file": "{os.path.basename(NOTEBOOK_PATH)}",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": true,
  "enable_gpu": true,
  "dataset_sources": ["{DATASET_SLUG}"]
}}
"""
    with open("notebook_dir/kernel-metadata.json", "w") as f:
        f.write(kernel_metadata)

    subprocess.run(["kaggle", "kernels", "push", "-p", "notebook_dir"], check=True)

# 3. Poll Kaggle until notebook execution finishes, then download outputs
def run_notebook():
    print("⏳ Waiting for Kaggle to finish execution...")
    for _ in range(30):  # ~15 mins max wait
        status = subprocess.run(
            ["kaggle", "kernels", "status", KERNEL_SLUG],
            capture_output=True,
            text=True
        )
        print(status.stdout.strip())

        if "complete" in status.stdout.lower():
            print("✅ Execution finished, downloading outputs...")
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            subprocess.run(
                ["kaggle", "kernels", "output", KERNEL_SLUG, "-p", OUTPUT_DIR],
                check=True
            )
            return
        elif "error" in status.stdout.lower():
            raise RuntimeError("❌ Kernel failed. Check Kaggle logs.")
        time.sleep(30)

    raise TimeoutError("⚠️ Kernel did not finish in time.")
