from fastapi import APIRouter,Depends
from ..config.database import get_db
from ..utils.auth import current,write_user
from ..schemas.measurement import MeasurementCreate,MeasurementReimport
from ..controllers import measurement_controller as controller
router=APIRouter(prefix="/measurements",tags=["measurements"])
@router.get("")
def listing(db=Depends(get_db),user=Depends(current)):return controller.list_all(db)
@router.get("/{ident}")
def detail(ident:str,db=Depends(get_db),user=Depends(current)):return controller.detail(db,ident)
@router.post("",status_code=201)
def create(body:MeasurementCreate,db=Depends(get_db),user=Depends(write_user)):return controller.create(db,body)
@router.put("/{ident}")
def reimport(ident:str,body:MeasurementReimport,db=Depends(get_db),user=Depends(write_user)):return controller.reimport(db,ident,body)
