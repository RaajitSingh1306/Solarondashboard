"""Solaron Solar Analytics & CRM Platform Package."""
__version__ = "2.0.0"

import sys
from pathlib import Path

# Add project root to sys.path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Subpackages
from . import core
from . import engines
from . import pipeline
from . import services
from . import extractors
from . import routes
from . import ui

# Aliases for backward compatibility
db = pipeline.db
data_quality = core.data_quality
analytics = core.analytics
ml_analytics = core.ml_analytics
crm = services.crm
scheduler = services.scheduler
geocode = services.geocode
contracts = core.contracts
metrics = core.metrics
physics = engines.physics
rpi = engines.rpi
lost_revenue = engines.lost_revenue
status_engine = engines.status_engine
fault_correlation = engines.fault_correlation
peer_group = core.peer_group
baseline = core.baseline
forecasting = core.forecasting
evaluation = core.evaluation
analytics_lake = core.analytics_lake
bronze = pipeline.bronze
data_audit = pipeline.data_audit

_COMPAT_MAP = {
    "db": db,
    "pipeline": pipeline,
    "bronze": bronze,
    "data_audit": data_audit,
    "analytics": analytics,
    "analytics_lake": analytics_lake,
    "baseline": baseline,
    "contracts": contracts,
    "data_quality": data_quality,
    "evaluation": evaluation,
    "forecasting": forecasting,
    "metrics": metrics,
    "ml_analytics": ml_analytics,
    "peer_group": peer_group,
    "fault_correlation": fault_correlation,
    "lost_revenue": lost_revenue,
    "physics": physics,
    "rpi": rpi,
    "status_engine": status_engine,
    "crm": crm,
    "geocode": geocode,
    "scheduler": scheduler,
}

for name, mod in _COMPAT_MAP.items():
    if name not in sys.modules:
        sys.modules[name] = mod
