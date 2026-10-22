"""Training script for fine-tuning YOLOv8 on the Road Damage / Pothole Dataset.

Executes all 50 epochs utilizing local NVIDIA RTX 4060 GPU with CUDA acceleration
and periodic checkpoint saving every 5 epochs.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import torch
from ultralytics import YOLO

ROOT_DIR = Path(__file__).resolve().parent
DATASET_YAML = ROOT_DIR / "datasets" / "rdd" / "data.yaml"


def main():
    parser = argparse.ArgumentParser(description="Train YOLOv8 on Pothole Dataset")
    parser.add_argument("--epochs", type=int, default=50, help="Number of training epochs (default: 50)")
    parser.add_argument("--batch", type=int, default=16, help="Batch size (default: 16)")
    parser.add_argument("--imgsz", type=int, default=640, help="Image resolution (default: 640)")
    parser.add_argument("--device", type=str, default="0", help="CUDA GPU device index (default: '0')")
    parser.add_argument("--workers", type=int, default=2, help="DataLoader workers (default: 2)")
    args = parser.parse_args()

    print("====================================================================")
    print(" AI POTHOLE DETECTION SYSTEM - 50-EPOCH GPU TRAINING")
    print("====================================================================")

    # 1. Hardware validation
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        vram_gb = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2)
        print(f"[+] Hardware Acceleration: CUDA ENABLED")
        print(f"[+] GPU Target:             {gpu_name} ({vram_gb} GB VRAM)")
    else:
        print("[-] Error: CUDA GPU not found. Aborting.")
        sys.exit(1)

    # 2. Dataset validation
    if not DATASET_YAML.exists():
        print(f"[-] Error: Could not locate dataset configuration at '{DATASET_YAML}'")
        sys.exit(1)

    print(f"[+] Dataset Config:         {DATASET_YAML}")
    print(f"[+] Target Epochs:          {args.epochs}")
    print(f"[+] Batch Size:             {args.batch}")
    print(f"[+] Input Resolution:       {args.imgsz}x{args.imgsz}")
    print(f"[+] Checkpoint Frequency:   Every 5 epochs")
    print("====================================================================\n")

    # 3. Initialize YOLOv8 Nano
    print("[*] Initializing YOLOv8n backbone...")
    model = YOLO("yolov8n.pt")

    # 4. Execute training with Perspective & Water Augmentations
    print("[*] Launching training loop with perspective & water augmentation on NVIDIA RTX 4060...")
    results = model.train(
        data=str(DATASET_YAML),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        project="runs/pothole_training",
        name="run_water_perspective",
        exist_ok=True,
        save=True,
        save_period=5,
        plots=True,
        # Augmentations for perspective distortion and specular water reflection invariance
        perspective=0.0015,  # 3D projective perspective distortion for non-vertical angles
        shear=12.0,          # Shear distortion to simulate angled windshield tilt (-12 to +12 deg)
        degrees=15.0,        # Random rotation (-15 to +15 deg)
        scale=0.5,           # Multi-scale training (0.5 to 1.5)
        hsv_s=0.7,           # Saturation jitter to handle wet dark asphalt vs bright dry roads
        hsv_v=0.4,           # Brightness jitter to handle water specular glare
        mosaic=1.0,          # 4-image mosaic blending
    )

    # 5. Export and copy best weights
    best_weights = ROOT_DIR / "runs" / "pothole_training" / "run_water_perspective" / "weights" / "best.pt"
    export_dir = ROOT_DIR / "weights"
    export_dir.mkdir(parents=True, exist_ok=True)
    target_weights = export_dir / "pothole_best.pt"

    if best_weights.exists():
        shutil.copy(best_weights, target_weights)
        print("\n====================================================================")
        print(" ALL 50 EPOCHS COMPLETED SUCCESSFULLY!")
        print("====================================================================")
        print(f"[+] Best Model Saved: {target_weights}")
        print("\nTo test your trained model with your webcam, run:")
        print(f"python -m edge_detection.detector --model weights/pothole_best.pt --device 0 --use-webcam")
        print("====================================================================")
    else:
        print("\n[!] Training finished. Check runs/pothole_training for results.")


if __name__ == "__main__":
    main()
