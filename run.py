"""
Solaron Root Runner.
Ensures correct PYTHONPATH and starts the Solaron FastAPI + NiceGUI server.
"""
import os
import sys
from pathlib import Path

# Add root directory and solaron directory to sys.path
cur_dir = Path(__file__).resolve().parent
if cur_dir.name == "solaron":
    solaron_dir = cur_dir
    root_dir = cur_dir.parent
else:
    root_dir = cur_dir
    solaron_dir = cur_dir / "solaron"

sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(solaron_dir))

cur_pythonpath = os.environ.get("PYTHONPATH", "")
os.environ["PYTHONPATH"] = f"{root_dir}{os.pathsep}{solaron_dir}{os.pathsep}{cur_pythonpath}"

if __name__ == "__main__":
    import uvicorn
    from solaron.config import settings

    print("\n" + "=" * 60)
    print("  SOLARON SOLAR ANALYTICS & CRM PLATFORM")
    print(f"  Open in browser: http://localhost:{settings.app_port} or http://127.0.0.1:{settings.app_port}")
    print("=" * 60 + "\n")

    uvicorn.run("solaron.app:app", host="127.0.0.1", port=settings.app_port, reload=True)
