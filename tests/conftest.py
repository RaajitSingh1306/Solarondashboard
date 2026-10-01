"""Pytest configuration and environment setup for Solaron test suite."""
import os
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Alias modules for backward compatibility during test discovery
import core
import engines
import pipeline
import services

_ALIASES = {
    "db": pipeline.db,
    "pipeline": pipeline,
    "bronze": pipeline.bronze,
    "data_audit": pipeline.data_audit,
    "analytics": core.analytics,
    "analytics_lake": core.analytics_lake,
    "baseline": core.baseline,
    "contracts": core.contracts,
    "data_quality": core.data_quality,
    "evaluation": core.evaluation,
    "forecasting": core.forecasting,
    "metrics": core.metrics,
    "ml_analytics": core.ml_analytics,
    "peer_group": core.peer_group,
    "fault_correlation": engines.fault_correlation,
    "lost_revenue": engines.lost_revenue,
    "physics": engines.physics,
    "rpi": engines.rpi,
    "status_engine": engines.status_engine,
    "crm": services.crm,
    "geocode": services.geocode,
    "scheduler": services.scheduler,
}

for name, mod in _ALIASES.items():
    if name not in sys.modules:
        sys.modules[name] = mod
