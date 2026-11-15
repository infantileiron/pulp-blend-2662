import json,hashlib
import numpy as np
from sqlalchemy import select,func
from src.config.database import initialize,Session
from src.models import PulpDataset,QualitySpec,BlendScenario,BlendRun,FormulaReview,Report,User,MeasurementSet,JointCalibration
from src.utils.security import hash_password
from src.services.run_service import compute
from src.services.joint_calibration import estimate
from src.services.calibration_service import ASSUMPTION,note_for

def make_materials():
 raw=[("P01","北杉针叶浆",5200,91,89,0,.65,3,1.5,0,200),("P02","南桉阔叶浆",3900,70,88,0,.7,3,2,0,160),("P03","高白竹浆",4200,74,91,0,.5,2.5,1.5,0,180),("P04","棉短绒浆",6500,98,94,0,.3,1.5,.8,0,250),("P05","净选回收浆",2600,56,74,.95,.6,4,3,.03,130),("P06","办公再生浆",3100,63,81,.88,.65,3,2,.04,150),("P07","未漂苇浆",2400,61,62,0,.25,4,3,0,120),("P08","机械木浆",2200,47,69,0,.25,5,3,0,100)]
 return [{"material_id":r[0],"name":r[1],"cost":r[2],"strength":r[3],"whiteness":r[4],"recycled":r[5],"min_share":0.,"max_share":r[6],"strength_width":r[7],"whiteness_width":r[8],"recycled_width":r[9],"cost_width":r[10]} for r in raw]

def make_measurements(materials):
 """24个检测批号的配对实测：共享批次因子使各原浆同涨同跌；两处缺测留空不补零。"""
 rng=np.random.default_rng(20261101);rows=[]
 for t in range(24):
  batch=f"B{t+1:03d}";factor=float(rng.normal(0,1));cost_factor=float(rng.normal(0,1))
  for m in materials:
   def val(center,width,f,lo,hi):return round(min(max(center+width*(.75*f+.55*float(rng.normal(0,1))),lo),hi),4)
   rows.append({"batch_id":batch,"material_id":m["material_id"],"strength":val(m["strength"],m["strength_width"],factor,0,100),"whiteness":val(m["whiteness"],m["whiteness_width"],factor,0,100),"recycled":val(m["recycled"],m["recycled_width"],factor,0,1) if m["recycled_width"]>0 else None,"cost":val(m["cost"],m["cost_width"],cost_factor,1,1e6)})
 rows[6*8+4]["whiteness"]=None
 rows[12*8+1]["strength"]=None
 return rows

def seed():
 initialize()
 with Session() as db:
  for role in ["admin","analyst","viewer"]:
   email=role+"@pulp.demo"
   if not db.scalar(select(User).where(User.email==email)):db.add(User(id="user-"+role,email=email,role=role,password_hash=hash_password("PulpDemo2026!")))
  if not db.get(PulpDataset,"demo-dataset"):db.add(PulpDataset(id="demo-dataset",name="岑岳十一月原浆报价与检测",materials=make_materials(),description="8种模拟原浆；文件cenyue_pulp_202611.csv；属性仅按声明线性混合"))
  if not db.get(QualitySpec,"demo-spec"):db.add(QualitySpec(id="demo-spec",name="文化用纸模拟质量窗口",strength_min=70,strength_max=100,whiteness_min=80,whiteness_max=100,recycled_min=.25,recycled_max=1,description="强度指数、白度%、回收纤维率分别限定；不作工业认证"))
  db.commit()
  if not db.get(BlendScenario,"demo-scenario"):db.add(BlendScenario(id="demo-scenario",name="名义低成本与固定配方扰动",dataset_id="demo-dataset",spec_id="demo-spec",n_samples=400,seed=20261112,perturb_cost=True))
  db.commit()
  if not db.get(BlendRun,"demo-run"):db.add(BlendRun(id="demo-run",scenario_id="demo-scenario",status="queued",result={},error=""));db.commit();compute(db,"demo-run")
  if not db.get(MeasurementSet,"demo-measurements"):
   rows=make_measurements(make_materials())
   canonical=json.dumps(rows,ensure_ascii=False,sort_keys=True)
   db.add(MeasurementSet(id="demo-measurements",name="十月配对检测批记录",version=1,content_hash=hashlib.sha256(canonical.encode()).hexdigest(),rows=rows,batches=24,description="24个检测批号×8种原浆的强度/白度/回收率/报价实测；两处缺测留空"))
   db.commit()
  if not db.get(JointCalibration,"demo-calibration"):
   ms=db.get(MeasurementSet,"demo-measurements");est=estimate(ms.rows)
   db.add(JointCalibration(id="demo-calibration",name="十月批次联合扰动校准",measurement_set_id=ms.id,source_version=ms.version,status="published" if est["ok"] else "invalid",reason=note_for(est),keys=est.get("keys",[]),matrix=est.get("matrix",[]),pair_counts=est.get("pair_counts",[]),key_counts=est.get("key_counts",{}),min_eigenvalue=est.get("min_eigenvalue"),method="Spearman秩相关（按检测批号成对完整样本，缺测不补零）" if est["ok"] else "",assumption=ASSUMPTION if est["ok"] else ""))
   db.commit()
  if not db.get(BlendScenario,"demo-scenario-joint"):db.add(BlendScenario(id="demo-scenario-joint",name="联合扰动下的固定配方试算",dataset_id="demo-dataset",spec_id="demo-spec",n_samples=400,seed=20261113,perturb_cost=True,calibration_id="demo-calibration"))
  db.commit()
  if not db.get(BlendRun,"demo-run-joint"):db.add(BlendRun(id="demo-run-joint",scenario_id="demo-scenario-joint",status="queued",inputs={"scenario_id":"demo-scenario-joint","scenario_name":"联合扰动下的固定配方试算","dataset_id":"demo-dataset","dataset_name":"岑岳十一月原浆报价与检测","spec_id":"demo-spec","spec_name":"文化用纸模拟质量窗口","mode":"joint","calibration_id":"demo-calibration","calibration_name":"十月批次联合扰动校准","calibration_source_version":1,"frozen_at":"2026-11-15T09:14:00Z"},result={},error=""));db.commit();compute(db,"demo-run-joint")
  if not db.get(FormulaReview,"demo-review"):db.add(FormulaReview(id="demo-review",run_id="demo-run",action="核查名义最优配方的活跃质量约束，并观察固定配方扰动通过数；线性混合和独立均匀误差仅为模拟假设。",state="approved",reviewer="admin@pulp.demo"))
  db.commit()
  if not db.get(Report,"demo-report"):db.add(Report(id="demo-report",review_id="demo-review",title="岑岳原浆配方稳健性底稿",snapshot={"result":db.get(BlendRun,"demo-run").result,"action":db.get(FormulaReview,"demo-review").action,"reviewer":"admin@pulp.demo"}))
  db.commit()
  return {cls.__tablename__:db.scalar(select(func.count()).select_from(cls)) for cls in [User,PulpDataset,QualitySpec,BlendScenario,BlendRun,FormulaReview,Report,MeasurementSet,JointCalibration]}
if __name__=="__main__":print(json.dumps(seed(),ensure_ascii=False))
