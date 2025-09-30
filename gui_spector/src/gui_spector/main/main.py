import threading
from gui_spector.computers.docker import DockerComputer
from gui_spector.verfication.agent import VerficationRunner
from pathlib import Path
import time

def acknowledge_safety_check_callback(message):
    print(f"Safety check: {message}")
    return True  # Always acknowledge for demo


def run_agent_instance(idx, user_message, start_url, data_dir, show_images, debug):
    display = f":{99 + idx}"
    container_name = "cua-sample-app"
    # Each runner gets its own subfolder for output
    runner_data_dir = data_dir / f"runner_{idx:03d}"
    runner_data_dir.mkdir(exist_ok=True, parents=True)
    print(f"[Runner {idx}] Using display {display}, container {container_name}, data dir {runner_data_dir}")
    computer = DockerComputer(container_name=container_name, display=display)
    with computer:
        runner = VerficationRunner(
            computer=computer,
            acknowledge_safety_check_callback=acknowledge_safety_check_callback,
            data_dir=runner_data_dir,
        )
        print(f"[Runner {idx}] All run data will be saved in: {runner.run_dir}")
        runner.run(
            user_message,
            print_steps=True,
            show_images=show_images,
            debug=debug,
            start_url=start_url,
        )


def main():
    num_runners = 3
    # --- Configuration ---
    START_URL = "https://www.amazon.com"
    SHOW_IMAGES = False
    DEBUG = False
    USER_MESSAGE = "go to https://www.amazon.com and search price for a honeywell h6 lamp"
    PACKAGE_ROOT = Path(__file__).resolve().parent.parent
    DATA_DIR = PACKAGE_ROOT / "resources" / "runs"
    print(f"DATA_DIR resolved to: {DATA_DIR}")
    # ---------------------
    threads = []
    for idx in range(num_runners):
        t = threading.Thread(
            target=run_agent_instance,
            args=(idx, USER_MESSAGE, START_URL, DATA_DIR, SHOW_IMAGES, DEBUG),
            daemon=False,
        )
        threads.append(t)
        t.start()
        time.sleep(1)
    for t in threads:
        t.join()

if __name__ == "__main__":
    main()
