import os
import time
import threading
import subprocess
import requests
import datetime

# Global flag to ensure threads only start once
_TASKS_STARTED = False

def keep_alive_loop():
    """Pings the Render URL every 10 minutes to prevent sleep."""
    render_url = os.environ.get('RENDER_EXTERNAL_URL')
    if not render_url:
        print("[Keep-Alive] No RENDER_EXTERNAL_URL found, skipping self-ping.")
        return
        
    print(f"[Keep-Alive] Starting loop to ping {render_url} every 10 minutes.")
    while True:
        try:
            time.sleep(10 * 60) # 10 minutes
            res = requests.get(render_url)
            print(f"[Keep-Alive] Pinged self: Status {res.status_code}")
        except Exception as e:
            print(f"[Keep-Alive] Ping failed: {e}")

def auto_train_and_push_loop():
    """Runs daily_auto_train.py and pushes to GitHub once a day."""
    github_token = os.environ.get('GITHUB_TOKEN')
    
    while True:
        # Check time, run at 03:00 UTC (Night time)
        now = datetime.datetime.utcnow()
        
        # If it's exactly the 3 AM hour (or whatever logic you prefer, let's just do every 24 hours for simplicity)
        # To make it robust, we sleep 24 hours between runs.
        print(f"[{now.isoformat()}] [Auto-Train] Sleeping for 24 hours until next training cycle...")
        time.sleep(24 * 60 * 60) # 24 hours
        
        print("[Auto-Train] Waking up to train model...")
        try:
            # 1. Run the training script
            subprocess.run(["python", "daily_auto_train.py"], check=True)
            print("[Auto-Train] Training script completed.")
            
            # 2. If Github Token exists, commit and push
            if github_token:
                print("[Auto-Train] GITHUB_TOKEN found. Committing to GitHub...")
                
                # Configure git
                subprocess.run(["git", "config", "--global", "user.email", "bot@render.com"])
                subprocess.run(["git", "config", "--global", "user.name", "Render Auto-Trainer Bot"])
                
                # Add files
                subprocess.run(["git", "add", "models/live_compatible_model.pkl", "collected_training_data.csv"])
                
                # Commit (allow empty if no changes)
                subprocess.run(["git", "commit", "-m", "Automated model training update [skip ci]"], check=False)
                
                # Push
                repo_url = f"https://{github_token}@github.com/Bikat1995/Football-Prediction-Ai.git"
                push_res = subprocess.run(["git", "push", repo_url, "HEAD:main"])
                if push_res.returncode == 0:
                    print("[Auto-Train] Successfully pushed updated model to GitHub!")
                else:
                    print("[Auto-Train] Git push failed.")
            else:
                print("[Auto-Train] No GITHUB_TOKEN environment variable. Cannot push to GitHub.")
                
        except Exception as e:
            print(f"[Auto-Train] Error during training/pushing cycle: {e}")

def start_background_tasks():
    global _TASKS_STARTED
    if _TASKS_STARTED:
        return
        
    _TASKS_STARTED = True
    print("Starting background tasks (Keep-alive and Auto-trainer)...")
    
    t1 = threading.Thread(target=keep_alive_loop, daemon=True)
    t1.start()
    
    t2 = threading.Thread(target=auto_train_and_push_loop, daemon=True)
    t2.start()
