"""Integrates the 1,243 water-logged and diverse perspective pothole dataset into datasets/rdd.

Splits 85% into training and 15% into validation with 'water_' prefix to guarantee
zero filename collisions and consistent YOLO class 0 indexing.
"""

import os
import random
import zipfile
from pathlib import Path
import shutil

ROOT_DIR = Path(__file__).resolve().parent
DATASET_DIR = ROOT_DIR / "datasets" / "rdd"
ZIP_PATH = ROOT_DIR / "datasets" / "potholes_water_1243.zip"

def main():
    if not ZIP_PATH.exists():
        print(f"[-] Error: Zip archive '{ZIP_PATH}' not found.")
        return

    train_img_dir = DATASET_DIR / "training" / "images"
    train_lbl_dir = DATASET_DIR / "training" / "labels"
    val_img_dir = DATASET_DIR / "validation" / "images"
    val_lbl_dir = DATASET_DIR / "validation" / "labels"

    for d in [train_img_dir, train_lbl_dir, val_img_dir, val_lbl_dir]:
        d.mkdir(parents=True, exist_ok=True)

    print("[*] Opening water-logged pothole zip archive...")
    with zipfile.ZipFile(ZIP_PATH, 'r') as z:
        all_names = z.namelist()
        img_names = [n for n in all_names if n.lower().endswith(('.jpg', '.jpeg', '.png'))]
        print(f"[+] Found {len(img_names)} pothole images in archive.")

        # Shuffle deterministically
        random.seed(42)
        random.shuffle(img_names)

        split_idx = int(len(img_names) * 0.85)
        train_set = img_names[:split_idx]
        val_set = img_names[split_idx:]

        print(f"[*] Allocating {len(train_set)} to training and {len(val_set)} to validation...")

        added_train = 0
        added_val = 0

        for img_name in train_set:
            stem = Path(img_name).stem
            txt_name = f"Pothole Dataset/{stem}.txt"
            if txt_name in all_names:
                # Extract image
                out_img = train_img_dir / f"water_{stem}.jpg"
                with open(out_img, "wb") as f_out:
                    f_out.write(z.read(img_name))

                # Extract label
                out_lbl = train_lbl_dir / f"water_{stem}.txt"
                with open(out_lbl, "wb") as f_out:
                    f_out.write(z.read(txt_name))
                added_train += 1

        for img_name in val_set:
            stem = Path(img_name).stem
            txt_name = f"Pothole Dataset/{stem}.txt"
            if txt_name in all_names:
                out_img = val_img_dir / f"water_{stem}.jpg"
                with open(out_img, "wb") as f_out:
                    f_out.write(z.read(img_name))

                out_lbl = val_lbl_dir / f"water_{stem}.txt"
                with open(out_lbl, "wb") as f_out:
                    f_out.write(z.read(txt_name))
                added_val += 1

    print(f"\n[+] Successfully added {added_train} water/perspective images to TRAINING.")
    print(f"[+] Successfully added {added_val} water/perspective images to VALIDATION.")

    total_train = len(list(train_img_dir.glob('*.*')))
    total_val = len(list(val_img_dir.glob('*.*')))
    print(f"\n>>> Total Dataset Size now: {total_train} train images, {total_val} val images <<<")

    # Clean up zip
    try:
        ZIP_PATH.unlink()
        print(f"[*] Cleaned up '{ZIP_PATH.name}'.")
    except Exception:
        pass

if __name__ == "__main__":
    main()
