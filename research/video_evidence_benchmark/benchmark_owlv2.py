import time
import psutil
from PIL import Image
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
import torch

def get_ram_mb():
    return psutil.Process().memory_info().rss / (1024 * 1024)

print("Starting OWLv2 CPU Benchmark...")
mem_start = get_ram_mb()
t0 = time.perf_counter()

model_id = "google/owlv2-base-patch16-ensemble"
print(f"Loading {model_id} on CPU...")
processor = AutoProcessor.from_pretrained(model_id)
model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id)
model.eval()

load_time = time.perf_counter() - t0
mem_after_load = get_ram_mb()
print(f"Model loaded in {load_time:.2f}s. RAM used: {mem_after_load - mem_start:.2f}MB")

# Test on frame
image = Image.open("research/video_evidence_benchmark/frame_tc5_01.jpg")
texts = [["glass vase", "wooden shelf", "wand boxes", "person"]]

t1 = time.perf_counter()
inputs = processor(text=texts, images=image, return_tensors="pt")
with torch.no_grad():
    outputs = model(**inputs)

infer_time = time.perf_counter() - t1
print(f"Inference latency on CPU: {infer_time*1000:.1f}ms")

target_sizes = torch.Tensor([image.size[::-1]])
results = processor.post_process_grounded_object_detection(
    outputs=outputs, target_sizes=target_sizes, threshold=0.15, text_labels=texts
)

boxes, scores, labels = results[0]["boxes"], results[0]["scores"], results[0]["labels"]
print(f"Detected {len(boxes)} entities:")
for box, score, label in zip(boxes[:5], scores[:5], labels[:5]):
    box = [round(i, 1) for i in box.tolist()]
    print(f"  - {label}: {score:.3f} at {box}")
