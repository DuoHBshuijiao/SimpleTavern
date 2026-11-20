"""Windows creation and shutdown policy for locally managed speech gateways."""
import os
import signal
import subprocess


def desktop_process_options(flags):
    if os.name != "nt" or os.environ.get("SIMPLETAVERN_DESKTOP") != "1":
        return {"creationflags": flags}
    return {"creationflags": subprocess.CREATE_NO_WINDOW, "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}


def terminate_windows_process(proc):
    if os.environ.get("SIMPLETAVERN_DESKTOP") != "1":
        proc.send_signal(signal.CTRL_BREAK_EVENT)
    elif proc.poll() is None:
        # A gateway script can own both a launcher and a GPU worker.
        subprocess.run(["taskkill.exe", "/PID", str(proc.pid), "/T", "/F"],
                       creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True,
                       timeout=12, check=False)
