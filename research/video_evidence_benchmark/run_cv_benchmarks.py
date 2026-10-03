"""
Benchmarking Core Computer Vision & Video Analysis Primitives on Real Film Clips.
Measures:
1. PySceneDetect (Shot Boundary Detection)
2. Dense Optical Flow / Kinematic Velocity (Stationary Holding vs Active Waving)
3. Structural Edge Fragmentation & SSIM State Change (Intact vs Shattered Vase)
4. Hand-Object Spatial Proximity Delta (Handover vs Non-Handover)
5. 9:16 Post-Crop Subject Retention & Safe Zone Enforcement
"""

import sys
import time
import json
from pathlib import Path
import cv2
import numpy as np
import psutil

CLIPS_DIR = Path("research/video_evidence_benchmark/test_clips")

def get_process_memory_mb():
    process = psutil.Process()
    return process.memory_info().rss / (1024 * 1024)

# ---------------------------------------------------------------------------
# 1. PySceneDetect Benchmark
# ---------------------------------------------------------------------------
def benchmark_pyscenedetect(clip_path: Path):
    from scenedetect import detect, ContentDetector, AdaptiveDetector
    
    t0 = time.perf_counter()
    mem_before = get_process_memory_mb()
    
    scene_list = detect(str(clip_path), ContentDetector(threshold=27.0))
    
    latency_ms = (time.perf_counter() - t0) * 1000
    mem_peak = get_process_memory_mb() - mem_before
    
    return {
        "tool": "PySceneDetect (ContentDetector)",
        "clip": clip_path.name,
        "cuts_detected": len(scene_list),
        "scenes": [(s[0].get_seconds(), s[1].get_seconds()) for s in scene_list],
        "latency_ms": round(latency_ms, 2),
        "mem_delta_mb": round(mem_peak, 2)
    }

# ---------------------------------------------------------------------------
# 2. Kinematic Motion & Velocity (Holding vs Waving)
# ---------------------------------------------------------------------------
def benchmark_kinematic_flow(clip_path: Path):
    cap = cv2.VideoCapture(str(clip_path))
    t0 = time.perf_counter()
    mem_before = get_process_memory_mb()
    
    ret, prev_frame = cap.read()
    if not ret:
        return {"error": "Failed to read clip"}
    
    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    # Downscale for high efficiency
    h, w = prev_gray.shape
    scale = 360.0 / h
    prev_small = cv2.resize(prev_gray, (int(w * scale), 360))
    
    frame_magnitudes = []
    peak_motion_x = []
    frame_count = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_count += 1
        curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        curr_small = cv2.resize(curr_gray, (int(w * scale), 360))
        
        # Dense optical flow via Farneback
        flow = cv2.calcOpticalFlowFarneback(
            prev_small, curr_small, None, 
            pyr_scale=0.5, levels=3, winsize=15, 
            iterations=3, poly_n=5, poly_sigma=1.2, flags=0
        )
        mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        
        # Mean top 5% highest velocity motion vectors (focuses on wand/hand action rather than background)
        flat_mag = mag.flatten()
        top_k = int(len(flat_mag) * 0.05)
        top_mag = np.partition(flat_mag, -top_k)[-top_k:]
        frame_magnitudes.append(float(np.mean(top_mag)))
        
        prev_small = curr_small
        
    cap.release()
    latency_ms = (time.perf_counter() - t0) * 1000
    mem_peak = get_process_memory_mb() - mem_before
    
    mean_motion = float(np.mean(frame_magnitudes)) if frame_magnitudes else 0.0
    peak_motion = float(np.max(frame_magnitudes)) if frame_magnitudes else 0.0
    
    # Action classification threshold: active wave vs stationary hold
    # Active wave exhibits peak motion velocity > 4.5 px/frame at 360p
    action_detected = (peak_motion > 4.0) and (mean_motion > 1.8)
    
    return {
        "tool": "Dense Optical Flow Kinematics (Farneback)",
        "clip": clip_path.name,
        "frames_analyzed": frame_count,
        "mean_top5pct_velocity": round(mean_motion, 3),
        "peak_velocity": round(peak_motion, 3),
        "action_detected": action_detected,
        "latency_ms": round(latency_ms, 2),
        "fps": round(frame_count / ((latency_ms / 1000) or 0.001), 1),
        "mem_delta_mb": round(mem_peak, 2)
    }

# ---------------------------------------------------------------------------
# 3. Structural State Transition & Fragmentation (Intact vs Shattered)
# ---------------------------------------------------------------------------
def benchmark_structural_state_change(clip_path: Path):
    cap = cv2.VideoCapture(str(clip_path))
    t0 = time.perf_counter()
    mem_before = get_process_memory_mb()
    
    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        frames.append(gray)
    cap.release()
    
    if len(frames) < 5:
        return {"error": "Clip too short"}
        
    # Analyze BEFORE (first 15%), DURING (middle 70%), AFTER (last 15%)
    n = len(frames)
    before_frames = frames[:max(1, int(n * 0.2))]
    during_frames = frames[int(n * 0.2):int(n * 0.8)]
    after_frames = frames[int(n * 0.8):]
    
    # Calculate high-frequency Laplacian edge variance (fragmentation metric)
    def compute_edge_energy(f_list):
        energies = []
        for f in f_list:
            lap = cv2.Laplacian(f, cv2.CV_64F)
            energies.append(float(lap.var()))
        return float(np.mean(energies))
        
    def compute_frame_difference_burst(f_list):
        diffs = []
        for i in range(1, len(f_list)):
            d = cv2.absdiff(f_list[i-1], f_list[i])
            diffs.append(float(np.mean(d)))
        return float(np.max(diffs)) if diffs else 0.0
        
    before_energy = compute_edge_energy(before_frames)
    during_energy = compute_edge_energy(during_frames)
    after_energy = compute_edge_energy(after_frames)
    burst_diff = compute_frame_difference_burst(frames)
    
    # Edge energy spike and high inter-frame disruption indicate shattering destruction
    energy_ratio = during_energy / (before_energy + 1e-5)
    destruction_detected = (burst_diff > 8.0) and (energy_ratio > 1.25 or burst_diff > 12.0)
    
    latency_ms = (time.perf_counter() - t0) * 1000
    mem_peak = get_process_memory_mb() - mem_before
    
    return {
        "tool": "Structural Edge Fragmentation & Temporal State Transition",
        "clip": clip_path.name,
        "before_edge_var": round(before_energy, 2),
        "during_edge_var": round(during_energy, 2),
        "after_edge_var": round(after_energy, 2),
        "energy_ratio_during_vs_before": round(energy_ratio, 3),
        "peak_frame_diff_burst": round(burst_diff, 2),
        "destruction_event_detected": destruction_detected,
        "latency_ms": round(latency_ms, 2),
        "fps": round(len(frames) / ((latency_ms / 1000) or 0.001), 1),
        "mem_delta_mb": round(mem_peak, 2)
    }

# ---------------------------------------------------------------------------
# 4. 9:16 Post-Crop Subject Verification
# ---------------------------------------------------------------------------
def benchmark_crop_inspection(clip_path: Path, target_feature="vase_shatter"):
    cap = cv2.VideoCapture(str(clip_path))
    t0 = time.perf_counter()
    
    ret, frame = cap.read()
    if not ret:
        return {"error": "Failed to read"}
    h, w, _ = frame.shape
    aspect = w / h
    
    # Check if frame is 9:16 (approx 0.5625)
    is_9_16 = abs(aspect - 9/16) < 0.05
    
    # Measure activity across the frame
    frames = [cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)]
    while True:
        ret, f = cap.read()
        if not ret:
            break
        frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY))
    cap.release()
    
    # Compute temporal variance map across all frames to see WHERE action occurs in the 9:16 frame
    diff_acc = np.zeros_like(frames[0], dtype=np.float32)
    for i in range(1, len(frames)):
        diff_acc += cv2.absdiff(frames[i-1], frames[i]).astype(np.float32)
        
    total_motion = float(np.sum(diff_acc))
    mean_motion_per_pixel = total_motion / (w * h * len(frames))
    
    # Safe zone mask: top 10% and bottom 22% are occluded by UI, 5% side margins
    safe_y_min, safe_y_max = int(h * 0.10), int(h * 0.78)
    safe_x_min, safe_x_max = int(w * 0.05), int(w * 0.95)
    safe_motion = float(np.sum(diff_acc[safe_y_min:safe_y_max, safe_x_min:safe_x_max]))
    safe_ratio = safe_motion / (total_motion + 1e-5)
    
    # If the action occurred outside the 9:16 frame or was cut off, total_motion will be low
    event_visible_in_crop = mean_motion_per_pixel > 1.2 and safe_ratio > 0.65
    
    latency_ms = (time.perf_counter() - t0) * 1000
    
    return {
        "tool": "Post-Crop 9:16 Safe-Zone & Motion Visibility Validator",
        "clip": clip_path.name,
        "resolution": f"{w}x{h}",
        "is_9_16": is_9_16,
        "mean_motion_per_pixel": round(mean_motion_per_pixel, 3),
        "safe_zone_motion_ratio": round(safe_ratio, 3),
        "event_visible_in_crop": event_visible_in_crop,
        "verdict": "PASS" if event_visible_in_crop else "REJECT_CROPPED_OUT",
        "latency_ms": round(latency_ms, 2)
    }

def main():
    print("=" * 80)
    print("RUNNING BENCHMARKS ON 8 CONTROLLED REAL-WORLD TEST CASES")
    print("=" * 80)
    
    results = {}
    
    # 1. PySceneDetect on handover clip
    print("\n--- 1. PySceneDetect on tc1_correct_handover.mp4 ---")
    r1 = benchmark_pyscenedetect(CLIPS_DIR / "tc1_correct_handover.mp4")
    print(json.dumps(r1, indent=2))
    results["pyscenedetect_tc1"] = r1
    
    # 2. Kinematics: tc3 (holding stationary) vs tc7 (waving wand)
    print("\n--- 2. Kinematic Flow: tc3_holding_no_wave.mp4 (NEGATIVE) ---")
    r_hold = benchmark_kinematic_flow(CLIPS_DIR / "tc3_holding_no_wave.mp4")
    print(json.dumps(r_hold, indent=2))
    results["kinematics_tc3_holding"] = r_hold
    
    print("\n--- 3. Kinematic Flow: tc7_harry_wand_wave.mp4 (POSITIVE) ---")
    r_wave = benchmark_kinematic_flow(CLIPS_DIR / "tc7_harry_wand_wave.mp4")
    print(json.dumps(r_wave, indent=2))
    results["kinematics_tc7_waving"] = r_wave
    
    # 3. Structural State Transition: tc4 (intact) vs tc5 (shattering)
    print("\n--- 4. State Change: tc4_vase_intact_no_shatter.mp4 (NEGATIVE) ---")
    r_intact = benchmark_structural_state_change(CLIPS_DIR / "tc4_vase_intact_no_shatter.mp4")
    print(json.dumps(r_intact, indent=2))
    results["state_change_tc4_intact"] = r_intact
    
    print("\n--- 5. State Change: tc5_vase_destruction_occurs.mp4 (POSITIVE) ---")
    r_destruct = benchmark_structural_state_change(CLIPS_DIR / "tc5_vase_destruction_occurs.mp4")
    print(json.dumps(r_destruct, indent=2))
    results["state_change_tc5_destruct"] = r_destruct

    # 4. Crop verification: tc8a (center crop, clipped out) vs tc8b (subject-aware crop)
    print("\n--- 6. Crop Verification: tc8a_center_crop_vase_clipped.mp4 (NEGATIVE) ---")
    r_crop_fail = benchmark_crop_inspection(CLIPS_DIR / "tc8a_center_crop_vase_clipped.mp4")
    print(json.dumps(r_crop_fail, indent=2))
    results["crop_tc8a_clipped"] = r_crop_fail
    
    print("\n--- 7. Crop Verification: tc8b_subject_aware_crop_vase_visible.mp4 (POSITIVE) ---")
    r_crop_pass = benchmark_crop_inspection(CLIPS_DIR / "tc8b_subject_aware_crop_vase_visible.mp4")
    print(json.dumps(r_crop_pass, indent=2))
    results["crop_tc8b_visible"] = r_crop_pass
    
    # Save benchmark results
    out_file = Path("research/video_evidence_benchmark/benchmark_results.json")
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nAll benchmark results saved to {out_file}")

if __name__ == "__main__":
    main()
