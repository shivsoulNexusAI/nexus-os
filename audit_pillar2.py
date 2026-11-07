import os
import gc
import psutil
import MetaTrader5 as mt5

print("\n=== PILLAR 2: RAM PROFILE & 1GB VPS THROTTLING AUDIT ===")

# 1. Inspect System Memory
mem = psutil.virtual_memory()
print(f"• Total Physical RAM : {mem.total / (1024**2):.1f} MB")
print(f"• Available RAM      : {mem.available / (1024**2):.1f} MB ({mem.percent}% used)")
print("-" * 55)

# 2. Inspect Running Process Footprints
print("• Live Trading & Automation Processes:")
total_quant_ram = 0.0
for p in psutil.process_iter(['pid', 'name', 'memory_info', 'cmdline']):
    try:
        p_name = p.info['name'] or ''
        cmd = ' '.join(p.info['cmdline'] or [])
        if 'terminal64' in p_name.lower() or 'python' in p_name.lower():
            rss_mb = p.info['memory_info'].rss / (1024**2)
            total_quant_ram += rss_mb
            desc = p_name
            if 'terminal64' in p_name.lower():
                # Extract terminal login / folder hint
                for part in cmd.split():
                    if 'MT5_' in part:
                        desc = f"MT5 [{part.split('\\')[-1]}]"
            elif 'python' in p_name.lower():
                for arg in p.info['cmdline'][1:]:
                    if arg.endswith('.py'):
                        desc = f"Python [{arg.split('\\')[-1]}]"
                        break
            print(f"   - PID {p.info['pid']:<6} | {rss_mb:>6.2f} MB | {desc}")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        continue

print(f"• Total Process Working Set: {total_quant_ram:.2f} MB")
print("-" * 55)

# 3. Apply Explicit Garbage Collection Benchmark
gc.set_threshold(700, 10, 5) # Tight thresholds for 1GB VPS
collected = gc.collect()
print(f"• Garbage Collection Engine: Tuned (Thresholds: 700/10/5 | Unreachable Freed: {collected})")
print("========================================================\n")