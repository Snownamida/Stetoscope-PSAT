import os
import subprocess

current_dir = os.path.dirname(os.path.abspath(__file__))
for folder in os.listdir(current_dir):
    extract_script = os.path.join(folder, "extract.py")
    if os.path.isfile(extract_script):
        print(f"执行 {extract_script}...")
        # 用 subprocess 执行 extract.py
        subprocess.run(["python", extract_script], check=True)
    else:
        print(f"{folder} 中没有 extract.py")
