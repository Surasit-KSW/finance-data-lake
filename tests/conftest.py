import sys
from pathlib import Path

# Allow importing from 04_Data_Pipelines/core/ as "core.*"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "04_Data_Pipelines"))

# Allow importing "script_catalog.*" from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
