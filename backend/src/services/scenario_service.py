from uuid import uuid4
from sqlalchemy import select
from fastapi import HTTPException
from ..models.scenario import BlendScenario
from ..models.dataset import PulpDataset
from ..models.spec import QualitySpec
from ..models.calibration import JointCalibration
from .calibration_service import require_usable
from .joint_calibration import active_dimension_keys

def create(db,body):
 data=db.get(PulpDataset,body.dataset_id)
 if not data or not db.get(QualitySpec,body.spec_id):raise HTTPException(422,"原浆数据或质量规格不存在")
 if db.scalar(select(BlendScenario).where(BlendScenario.name==body.name)):raise HTTPException(409,"试算情景名称已存在")
 if body.calibration_id:
  cal=require_usable(db,db.get(JointCalibration,body.calibration_id))
  missing=[k for k in active_dimension_keys(data.materials,body.perturb_cost) if k not in cal.keys]
  if missing:raise HTTPException(422,"校准未覆盖情景扰动维度："+"、".join(missing[:6])+"；请换用覆盖更全的校准或关闭成本扰动")
 row=BlendScenario(id=str(uuid4()),**body.model_dump());db.add(row);db.commit();return row
