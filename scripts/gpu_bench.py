"""
Rough GPU capability benchmark - no downloads, no dataset needed.
Measures matmul FLOPS and conv2d throughput at 640x640, then estimates
training time for: batch=10, img=640x640, 100 epochs, ~2GB dataset.
"""
import time
import torch

assert torch.cuda.is_available(), "No CUDA GPU detected"
dev = torch.device("cuda")
name = torch.cuda.get_device_name(0)
props = torch.cuda.get_device_properties(0)
print(f"GPU: {name}  |  VRAM: {props.total_memory/1e9:.1f} GB  |  SM count: {props.multi_processor_count}")

def bench_matmul(dtype, n=8192, iters=20):
    a = torch.randn(n, n, device=dev, dtype=dtype)
    b = torch.randn(n, n, device=dev, dtype=dtype)
    torch.cuda.synchronize()
    t0 = time.time()
    for _ in range(iters):
        c = a @ b
    torch.cuda.synchronize()
    dt = time.time() - t0
    flops = 2 * n**3 * iters
    tflops = flops / dt / 1e12
    return tflops

def bench_conv(batch=10, img=640, iters=30):
    x = torch.randn(batch, 3, img, img, device=dev)
    conv = torch.nn.Sequential(
        torch.nn.Conv2d(3, 64, 3, 2, 1),
        torch.nn.Conv2d(64, 128, 3, 2, 1),
        torch.nn.Conv2d(128, 256, 3, 2, 1),
        torch.nn.Conv2d(256, 256, 3, 1, 1),
    ).to(dev)
    opt = torch.optim.SGD(conv.parameters(), lr=0.01)
    torch.cuda.synchronize()
    t0 = time.time()
    for _ in range(iters):
        opt.zero_grad()
        y = conv(x)
        loss = y.sum()
        loss.backward()
        opt.step()
    torch.cuda.synchronize()
    dt = time.time() - t0
    imgs_per_sec = (batch * iters) / dt
    return imgs_per_sec

print("\n--- Raw compute ---")
fp32 = bench_matmul(torch.float32)
print(f"FP32 matmul: {fp32:.1f} TFLOPS")
try:
    fp16 = bench_matmul(torch.float16)
    print(f"FP16 matmul: {fp16:.1f} TFLOPS")
except Exception as e:
    print(f"FP16 skipped: {e}")

print("\n--- Conv training-step throughput (batch=10, 640x640) ---")
ips = bench_conv(batch=10, img=640)
print(f"~{ips:.1f} images/sec (toy conv stack, forward+backward+step)")

# ---- Rough training-time estimate for the user's job ----
dataset_gb = 2.0
avg_img_kb = 150  # typical compressed jpg at 640px
approx_images = int(dataset_gb * 1024 * 1024 / avg_img_kb)
epochs = 100

# Real YOLO-class models run slower than this toy conv stack due to depth/necks/heads.
# Rule of thumb: real detector throughput is roughly 0.15-0.35x this toy benchmark on the same GPU.
for frac, label in [(0.30, "optimistic (small model, e.g. yolov8n/s)"),
                     (0.18, "typical (medium model, e.g. yolov8m)"),
                     (0.10, "conservative (large model, e.g. yolov8l/x)")]:
    real_ips = ips * frac
    sec_per_epoch = approx_images / real_ips
    total_hr = sec_per_epoch * epochs / 3600
    print(f"\n[{label}]")
    print(f"  ~{real_ips:.1f} img/s  ->  {sec_per_epoch:.0f}s/epoch  ->  ~{total_hr:.1f} hours for {epochs} epochs (~{approx_images} images/epoch)")

print("\nNote: these are rough order-of-magnitude estimates from synthetic ops, not your actual model.")
print("Actual time depends heavily on model architecture, augmentation, dataloader/IO speed, and mixed precision use.")
