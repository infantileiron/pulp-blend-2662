from ..services import calibration_service
from ..models.calibration import JointCalibration
from ..models.common import serialize
from .common import listing,require
def list_all(db):return listing(db,JointCalibration)
def detail(db,ident):return serialize(require(db,JointCalibration,ident))
def create(db,body):return serialize(calibration_service.create(db,body))
def publish(db,ident):return serialize(calibration_service.publish(db,ident))
