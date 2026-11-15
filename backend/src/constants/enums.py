from enum import StrEnum
class Role(StrEnum):
 ADMIN="admin"
 ANALYST="analyst"
 VIEWER="viewer"
class RunStatus(StrEnum):
 QUEUED="queued"
 RUNNING="running"
 COMPLETED="completed"
 INFEASIBLE="infeasible"
 FAILED="failed"
PROPERTIES=["strength","whiteness","recycled"]
PHYSICAL_BOUNDS={"strength":(0.,100.),"whiteness":(0.,100.),"recycled":(0.,1.)}

CONSTRAINT_TOLERANCE=1e-7

# 联合扰动校准：估计口径与生命周期
MEASUREMENT_PROPERTIES=PROPERTIES+["cost"]
JOINT_MIN_OBS=8
JOINT_MIN_PAIRS=6
JOINT_EIGEN_TOLERANCE=1e-10
JOINT_REPAIR_FLOOR=-0.05
JOINT_REPAIR_MAX_ADJUST=0.1
CALIBRATION_STATUSES=["draft","published","stale","invalid"]
