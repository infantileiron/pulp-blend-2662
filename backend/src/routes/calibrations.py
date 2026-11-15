from fastapi import APIRouter,Depends
from ..config.database import get_db
from ..utils.auth import current,write_user
from ..schemas.calibration import CalibrationCreate
from ..controllers import calibration_controller as controller
router=APIRouter(prefix="/calibrations",tags=["calibrations"])
@router.get("")
def listing(db=Depends(get_db),user=Depends(current)):return controller.list_all(db)
@router.get("/{ident}")
def detail(ident:str,db=Depends(get_db),user=Depends(current)):return controller.detail(db,ident)
@router.post("",status_code=201)
def create(body:CalibrationCreate,db=Depends(get_db),user=Depends(write_user)):return controller.create(db,body)
@router.post("/{ident}/publish")
def publish(ident:str,db=Depends(get_db),user=Depends(write_user)):return controller.publish(db,ident)
