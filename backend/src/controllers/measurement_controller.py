from ..services import measurement_service
from ..models.measurement import MeasurementSet
from ..models.common import serialize
from .common import listing,require
def list_all(db):return listing(db,MeasurementSet)
def detail(db,ident):return serialize(require(db,MeasurementSet,ident))
def create(db,body):return serialize(measurement_service.create(db,body))
def reimport(db,ident,body):return serialize(measurement_service.reimport(db,ident,body))
