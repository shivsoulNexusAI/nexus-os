import subprocess
import sys
import time
import os

BASE_DIR = r"C:\Quant-Nexus-Eng\Quant-Nexus-Telegram-bot"
PYTHON_EXE = sys.executable

WORKERS = [
    ("bridge_server.py", [PYTHON_EXE, "bridge_server.py"]),
    ("engine_algorithmic.py", [PYTHON_EXE, "engine_algorithmic.py"]),
    ("telegram_bot.py", [PYTHON_EXE, "telegram_bot.py"]),
    ("trade_manager.py", [PYTHON_EXE, "trade_manager.py"]),
    ("copier_master.py", [PYTHON_EXE, "copier_master.py"]),
    ("slave_01", [PYTHON_EXE, "slave_worker.py", "--id", "Slave_01", "--path", r"C:\MT5_Terminals\Slave_01\terminal64.exe", "--multiplier", "0.5"]),
    ("slave_02", [PYTHON_EXE, "slave_worker.py", "--id", "Slave_02", "--path", r"C:\MT5_Terminals\Slave_02\terminal64.exe", "--multiplier", "1.0"]),
]

def launch_workers():
    processes = []
    for name, cmd in WORKERS:
        script_file = cmd[1]
        script_path = os.path.join(BASE_DIR, script_file)
        if os.path.exists(script_path):
            print(f"🚀 Spawning daemon: {name}")
            proc = subprocess.Popen(cmd, cwd=BASE_DIR)
            processes.append((name, cmd, proc))
        else:
            print(f"⚠️ Script not found, skipping: {script_path}")
    return processes

def supervise():
    print("🛡️ Quant Nexus Multi-Account Supervisor Started.")
    active_workers = launch_workers()

    try:
        while True:
            time.sleep(5)
            for i, (name, cmd, proc) in enumerate(active_workers):
                poll = proc.poll()
                if poll is not None:
                    print(f"⚠️ Worker [{name}] exited (Code: {poll}). Respawning in 3s...")
                    time.sleep(3)
                    new_proc = subprocess.Popen(cmd, cwd=BASE_DIR)
                    active_workers[i] = (name, cmd, new_proc)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down supervisor and worker fleet...")
        for name, _, proc in active_workers:
            proc.terminate()
        sys.exit(0)

if __name__ == "__main__":
    supervise()
