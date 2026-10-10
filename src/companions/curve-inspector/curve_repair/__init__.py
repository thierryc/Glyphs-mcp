"""Shared Curve Inspector repair engine; native/UI dependencies are lazy."""

ENGINE_VERSION = "0.5.0"
SUPERTOOL_REVISION = "ccc71ee39ef72c0c34267410d2b9ebee454ec98c"

from .geometry import RepairError, diagnose_join, deviation, integrated_difference
from .supertool import harmonize, balance

__all__ = ["ENGINE_VERSION", "SUPERTOOL_REVISION", "RepairError", "diagnose_join",
           "deviation", "integrated_difference", "harmonize", "balance"]
