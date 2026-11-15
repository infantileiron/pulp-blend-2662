from uuid import uuid4
from sqlalchemy import select
from fastapi import HTTPException
from ..models.run import BlendRun
from ..models.scenario import BlendScenario
from ..models.dataset import PulpDataset
from ..models.spec import QualitySpec
from ..models.calibration import JointCalibration
from ..models.common import now
from ..constants.enums import PROPERTIES
from ..utils.queue import enqueue
from .calibration_service import require_usable
from .linear_blend import solve
from .lhs_robustness import simulate

def create(db,body):
 scenario=db.get(BlendScenario,body.scenario_id)
 if not scenario:raise HTTPException(422,"试算情景不存在")
 data=db.get(PulpDataset,scenario.dataset_id);spec_row=db.get(QualitySpec,scenario.spec_id)
 cal=None
 if scenario.calibration_id:
  locked=db.execute(select(JointCalibration).where(JointCalibration.id==scenario.calibration_id).with_for_update()).scalar_one_or_none()
  cal=require_usable(db,locked)
 frozen={"scenario_id":scenario.id,"scenario_name":scenario.name,"dataset_id":data.id,"dataset_name":data.name,"spec_id":spec_row.id,"spec_name":spec_row.name,"mode":"joint" if cal else "independent","calibration_id":cal.id if cal else None,"calibration_name":cal.name if cal else None,"calibration_source_version":cal.source_version if cal else None,"frozen_at":now().isoformat()+"Z"}
 row=BlendRun(id=str(uuid4()),scenario_id=body.scenario_id,status="queued",inputs=frozen,result={},error="");db.add(row);db.commit()
 try:enqueue(row.id)
 except Exception:
  row.status="failed";row.error="Redis队列不可用，请稍后重试";db.commit();raise HTTPException(503,row.error)
 return row

def compute(db,run_id):
 row=db.get(BlendRun,run_id)
 if row is None or row.status not in ["queued","running"]:return
 row.status="running";db.commit()
 try:
  scenario=db.get(BlendScenario,row.scenario_id);data=db.get(PulpDataset,scenario.dataset_id);spec_row=db.get(QualitySpec,scenario.spec_id)
  joint=None
  if scenario.calibration_id:
   cal=db.get(JointCalibration,scenario.calibration_id)
   if cal is None:raise ValueError("情景引用的联合校准记录不存在")
   joint={"calibration_id":cal.id,"calibration_name":cal.name,"source_version":cal.source_version,"keys":cal.keys,"matrix":cal.matrix,"pair_counts":cal.pair_counts,"key_counts":cal.key_counts,"min_eigenvalue":cal.min_eigenvalue}
  spec={key+"_"+side:getattr(spec_row,key+"_"+side) for key in PROPERTIES for side in ["min","max"]};lp=solve(data.materials,spec)
  robust=simulate(data.materials,[r["share"] for r in lp["shares"]],spec,scenario.n_samples,scenario.seed,scenario.perturb_cost,joint=joint) if lp["feasible"] else None
  row.result={"inputs":row.inputs,"dataset_name":data.name,"spec_name":spec_row.name,"scenario_name":scenario.name,"spec":spec,"lp":lp,"robustness":robust,"materials":data.materials,"cost_unit":"CNY/tonne","property_units":{"strength":"模拟强度指数","whiteness":"%","recycled":"fraction"}};row.status="completed" if lp["feasible"] else "infeasible"
 except Exception as e:row.status="failed";row.error=str(e)[:1000]
 db.commit()
