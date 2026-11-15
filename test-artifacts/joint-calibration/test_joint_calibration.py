# 联合扰动校准验证：完全正负相关、缺测不补零、样本不足、非半正定、
# 发布争抢、源数据失效与成套冻结、均匀边际与分层保留。
import threading,uuid
import numpy as np
import pytest
from scipy.stats import spearmanr
from fastapi import HTTPException
from src.config.database import Session
from src.models import MeasurementSet,JointCalibration,PulpDataset,QualitySpec,BlendScenario,BlendRun
from src.models.common import serialize
from src.schemas.measurement import MeasurementCreate,MeasurementReimport
from src.schemas.calibration import CalibrationCreate
from src.schemas.scenario import ScenarioCreate
from src.schemas.run import RunCreate
from src.services import measurement_service,calibration_service,scenario_service,run_service
from src.services.joint_calibration import estimate,nearest_correlation,iman_conover
from src.services.lhs_robustness import latin_hypercube,simulate
from src.services.paired_measurements import parse_csv

def uniq(tag):return tag+"-"+uuid.uuid4().hex[:8]

def csv_of(rows,cols=("batch_id","material_id","strength","whiteness","recycled","cost")):
 return "\n".join([",".join(cols)]+[",".join("" if r.get(c) is None else str(r[c]) for c in cols) for r in rows])

def paired_rows(n=12,materials=("A","B"),missing=()):
 """n个完整批次的配对实测；共享批次因子使各维同涨同跌。missing={(批,料,列)}置缺测。"""
 rows=[]
 for t in range(1,n+1):
  for mi,m in enumerate(materials):
   row={"batch_id":f"B{t:02d}","material_id":m,"strength":50.+2*t+mi,"whiteness":60.+1.5*t-mi,"recycled":round(.3+.02*t+.01*mi,4),"cost":100.+5*t+10*mi}
   for col in ("strength","whiteness","recycled","cost"):
    if (t,m,col) in missing:row[col]=None
   rows.append(row)
 return rows

MATS=[{"material_id":"A","name":"甲浆","cost":100.,"min_share":0.,"max_share":1.,"strength":50.,"whiteness":60.,"recycled":.4,"strength_width":5.,"whiteness_width":4.,"recycled_width":.05,"cost_width":10.},{"material_id":"B","name":"乙浆","cost":200.,"min_share":0.,"max_share":1.,"strength":70.,"whiteness":70.,"recycled":.6,"strength_width":6.,"whiteness_width":3.,"recycled_width":.05,"cost_width":12.}]
SPEC={"strength_min":0.,"strength_max":100.,"whiteness_min":0.,"whiteness_max":100.,"recycled_min":0.,"recycled_max":1.}

def make_calibration(db,rows=None,status="published"):
 ms=measurement_service.create(db,MeasurementCreate(name=uniq("实测"),csv_text=csv_of(rows or paired_rows()),description=""))
 cal=calibration_service.create(db,CalibrationCreate(name=uniq("校准"),measurement_set_id=ms.id))
 assert cal.status=="draft",cal.reason
 if status=="published":cal=calibration_service.publish(db,cal.id)
 return ms,cal

def make_scenario(db,calibration_id=None):
 data=PulpDataset(id=uniq("ds"),name=uniq("批次"),materials=MATS,description="");db.add(data)
 spec=QualitySpec(id=uniq("sp"),name=uniq("窗口"),**SPEC,description="");db.add(spec);db.commit()
 body=ScenarioCreate(name=uniq("情景"),dataset_id=data.id,spec_id=spec.id,n_samples=60,seed=7,perturb_cost=True,calibration_id=calibration_id)
 return scenario_service.create(db,body)

# ---------- 估计层：完全正负相关 / 缺测 / 样本不足 / 非半正定 ----------

def test_perfect_positive_and_negative_correlation():
 rows=[]
 for t in range(1,11):
  rows.append({"batch_id":f"B{t:02d}","material_id":"A","strength":10.*t,"whiteness":100.-3.*t,"recycled":None,"cost":None})
  rows.append({"batch_id":f"B{t:02d}","material_id":"B","strength":5.*t,"whiteness":None,"recycled":None,"cost":None})
 est=estimate(rows)
 assert est["ok"] and not est["adjusted"]
 keys=est["keys"];m=np.array(est["matrix"])
 i,j=keys.index("A:strength"),keys.index("B:strength")
 assert m[i,j]==pytest.approx(1.0)            # 完全正相关
 k=keys.index("A:whiteness")
 assert m[i,k]==pytest.approx(-1.0) and m[j,k]==pytest.approx(-1.0)  # 完全负相关
 assert est["min_eigenvalue"]>=-1e-10         # 完全相关仍为半正定，可实现

def test_missing_cells_pairwise_not_zero_filled():
 missing={(9,"A","whiteness"),(10,"A","whiteness"),(10,"B","cost")}
 est=estimate(paired_rows(12,missing=missing))
 assert est["ok"]
 keys=est["keys"];counts=np.array(est["pair_counts"])
 i=keys.index("A:whiteness")
 assert counts[i,i]==0
 for j,k in enumerate(keys):
  if k!="A:whiteness":assert counts[i,j]==10  # 两批缺测只减少成对样本，不补零
 j=keys.index("B:cost");assert counts[i,j]==10
 # 对照：若把缺测补零，相关会被拉低；成对完整样本下两列同序，秩相关恰为1
 mono=[{"batch_id":f"B{t:02d}","material_id":"A","strength":float(t),"whiteness":float(t) if t<=8 else None,"recycled":None,"cost":None} for t in range(1,11)]
 mono+=[{"batch_id":f"B{t:02d}","material_id":"B","strength":2.*t,"whiteness":None,"recycled":None,"cost":None} for t in range(1,11)]
 est2=estimate(mono);k2=est2["keys"]
 got=est2["matrix"][k2.index("A:strength")][k2.index("A:whiteness")]
 assert got==pytest.approx(1.0)               # 缺测两批未补零，否则秩相关必然<1
 assert est2["pair_counts"][k2.index("A:strength")][k2.index("A:whiteness")]==8

def test_insufficient_samples_explained():
 est=estimate(paired_rows(5))                 # 每维仅5条<8
 assert not est["ok"] and "有效样本不足" in est["reason"]
 missing={(t,"A","whiteness") for t in range(1,5)}|{(t,"B","strength") for t in range(9,13)}
 est=estimate(paired_rows(12,missing=missing))  # 两维各8条实测，但交集仅4批<6
 assert not est["ok"] and "成对完整样本" in est["reason"] and "不补零" in est["reason"]

def test_unrealizable_correlation_explained_not_faked():
 rows=[]
 for t in range(1,25):
  b=f"B{t:02d}"
  if t<=16:rows.append({"batch_id":b,"material_id":"A","strength":float(t),"whiteness":None,"recycled":None,"cost":None})
  if t<=8 or t>=17:rows.append({"batch_id":b,"material_id":"B","strength":float(t),"whiteness":None,"recycled":None,"cost":None})
  if t>=9:rows.append({"batch_id":b,"material_id":"C","strength":float(t) if t<=16 else float(25-t),"whiteness":None,"recycled":None,"cost":None})
 est=estimate(rows)                           # 成对看ρ(A,B)=ρ(A,C)=+1而ρ(B,C)=-1：非半正定
 assert not est["ok"] and "非半正定" in est["reason"] and "不以独立抽样冒充联合扰动" in est["reason"]

def test_disclosed_repair_for_marginally_unrealizable():
 from scripts.seed_demo import make_materials,make_measurements
 est=estimate(make_measurements(make_materials()))   # 26维×24批+两处缺测：原始估计轻微非半正定
 assert est["ok"] and est["adjusted"]
 assert est["raw_min_eigenvalue"]<0 and est["min_eigenvalue"]>=-1e-10
 assert est["max_adjustment"]<=0.1
 m=np.array(est["matrix"]);assert np.linalg.eigvalsh(m).min()>=-1e-9  # 修复后可实现

def test_constant_dimensions_dropped_with_disclosure():
 rows=paired_rows(12)
 for r in rows:r["recycled"]=.5               # 常量维度
 est=estimate(rows)
 assert est["ok"] and "A:recycled" in est["dropped"] and "A:recycled" not in est["keys"]

def test_constant_within_pair_intersection_explained():
 rows=[]
 for t in range(1,13):
  rows.append({"batch_id":f"B{t:02d}","material_id":"A","strength":float(t),"whiteness":float(t) if t<=8 else None,"recycled":None,"cost":None})
  rows.append({"batch_id":f"B{t:02d}","material_id":"B","strength":float(t),"whiteness":5. if t<=8 else float(t),"recycled":None,"cost":None})
 est=estimate(rows)                           # 交集内一列常量，秩相关无定义，不得让NaN穿透
 assert not est["ok"] and "常量" in est["reason"]

# ---------- 抽样层：联合扰动保留均匀边际与每维分层 ----------

def joint_payload(est):
 return {"calibration_id":"c1","calibration_name":"t","source_version":1,"keys":est["keys"],"matrix":est["matrix"],"pair_counts":est["pair_counts"],"key_counts":est["key_counts"],"min_eigenvalue":est["min_eigenvalue"]}

def test_iman_conover_preserves_stratified_uniform_marginals():
 rng_u=latin_hypercube(200,3,42)
 target=[[1.,.8,-.6],[.8,1.,-.5],[-.6,-.5,1.]]
 out,actual=iman_conover(rng_u,target,7)
 for j in range(3):assert np.allclose(np.sort(out[:,j]),np.sort(rng_u[:,j]))  # 每列取值集合不变
 for j in range(3):                                                           # 每维仍每层恰一个样本：分层保留
  strata=np.floor(out[:,j]*200);assert sorted(strata)==list(range(200))
 for a in range(3):
  for b in range(a+1,3):assert actual[a,b]==pytest.approx(target[a][b],abs=.1)

def test_simulate_joint_reaches_perfect_correlation():
 rows=[]
 for t in range(1,11):rows.append({"batch_id":f"B{t:02d}","material_id":"A","strength":10.*t,"whiteness":100.-3.*t,"recycled":None,"cost":None})
 est=estimate(rows)
 mats=[dict(MATS[0],recycled_width=0.,cost_width=0.)]
 r=simulate(mats,[1.],SPEC,80,11,False,joint=joint_payload(est))
 j=r["joint"]
 assert r["mode"]=="joint" and j["keys"]==["A:strength","A:whiteness"]
 assert j["actual"][0][1]==pytest.approx(-1.,abs=1e-9)   # 完全负相关精确实现
 assert j["target"][0][1]==pytest.approx(-1.)
 assert j["min_pair_n"]==10 and j["constant_keys"]==["A:recycled"]
 base=simulate(mats,[1.],SPEC,80,11,False)                # 同seed独立模式
 assert base["mode"]=="independent" and base["joint"] is None and "独立均匀" in base["assumption"]

# ---------- 生命周期：发布争抢 / 源数据失效 / 成套冻结 ----------

def test_publish_contention_single_winner(db):
 ms,cal=make_calibration(db,status="draft")
 barrier=threading.Barrier(2);outcome=[]
 def race():
  barrier.wait()
  with Session() as s:
   try:calibration_service.publish(s,cal.id);outcome.append("ok")
   except HTTPException as e:outcome.append(e.status_code)
 ts=[threading.Thread(target=race) for _ in range(2)]
 [t.start() for t in ts];[t.join() for t in ts]
 assert outcome.count("ok")==1 and outcome.count(409)==1  # 并发发布只有一个生效
 with Session() as s:assert s.get(JointCalibration,cal.id).status=="published"  # 失败保留旧版

def test_publish_rejects_invalid_and_stale(db):
 ms=measurement_service.create(db,MeasurementCreate(name=uniq("实测"),csv_text=csv_of(paired_rows(5)),description=""))
 cal=calibration_service.create(db,CalibrationCreate(name=uniq("校准"),measurement_set_id=ms.id))
 assert cal.status=="invalid" and "有效样本不足" in cal.reason
 with pytest.raises(HTTPException) as e:calibration_service.publish(db,cal.id)
 assert e.value.status_code==409
 ms2,cal2=make_calibration(db)
 measurement_service.reimport(db,ms2.id,MeasurementReimport(csv_text=csv_of(paired_rows(13))))
 assert db.get(JointCalibration,cal2.id).status=="stale"  # 源数据更新使旧校准失效
 with pytest.raises(HTTPException) as e2:calibration_service.publish(db,cal2.id)
 assert e2.value.status_code==409

def test_reimport_same_content_rejected(db):
 ms,_=make_calibration(db)
 with pytest.raises(HTTPException) as e:measurement_service.reimport(db,ms.id,MeasurementReimport(csv_text=csv_of(paired_rows(12))))
 assert e.value.status_code==409 and db.get(MeasurementSet,ms.id).version==1  # 失败保留旧版

def test_run_freezes_inputs_and_stale_calibration_rejected(db):
 ms,cal=make_calibration(db)
 scenario=make_scenario(db,calibration_id=cal.id)
 run=run_service.create(db,RunCreate(scenario_id=scenario.id))
 frozen=run.inputs
 assert frozen["mode"]=="joint" and frozen["calibration_id"]==cal.id and frozen["calibration_source_version"]==1
 assert frozen["dataset_id"] and frozen["spec_id"] and frozen["frozen_at"]     # 输入及校准版本成套冻结
 run_service.compute(db,run.id)
 assert run.status=="completed"
 rob=run.result["robustness"];j=rob["joint"]
 assert rob["mode"]=="joint" and j["calibration_id"]==cal.id
 assert len(j["target"])==len(j["actual"])==len(j["keys"]) and j["min_pair_n"]>=6  # 底稿：目标与实际相关性、有效样本数
 assert run.result["inputs"]["calibration_source_version"]==1
 measurement_service.reimport(db,ms.id,MeasurementReimport(csv_text=csv_of(paired_rows(14))))
 assert db.get(JointCalibration,cal.id).status=="stale"
 with pytest.raises(HTTPException) as e:run_service.create(db,RunCreate(scenario_id=scenario.id))
 assert e.value.status_code==409 and "失效" in e.value.detail                  # 旧校准拒绝新试算
 with pytest.raises(HTTPException) as e2:scenario_service.create(db,ScenarioCreate(name=uniq("情景"),dataset_id=scenario.dataset_id,spec_id=scenario.spec_id,n_samples=60,seed=7,perturb_cost=True,calibration_id=cal.id))
 assert e2.value.status_code==409
 again=serialize(db.get(BlendRun,run.id))
 assert again["status"]=="completed" and again["result"]["robustness"]["mode"]=="joint"  # 已完成结果仍可回读

def test_draft_calibration_and_uncovered_dimensions_rejected(db):
 ms,cal=make_calibration(db,status="draft")
 with pytest.raises(HTTPException) as e:make_scenario(db,calibration_id=cal.id)
 assert e.value.status_code==409 and "草稿" in e.value.detail
 rows=[{**r,"cost":None} for r in paired_rows(12)]      # 无成本实测，覆盖不了成本扰动维
 ms2=measurement_service.create(db,MeasurementCreate(name=uniq("实测"),csv_text=csv_of(rows),description=""))
 cal2=calibration_service.create(db,CalibrationCreate(name=uniq("校准"),measurement_set_id=ms2.id))
 calibration_service.publish(db,cal2.id)
 with pytest.raises(HTTPException) as e2:make_scenario(db,calibration_id=cal2.id)
 assert e2.value.status_code==422 and "未覆盖" in e2.value.detail

def test_independent_mode_stays_honest(db):
 scenario=make_scenario(db,calibration_id=None)
 run=run_service.create(db,RunCreate(scenario_id=scenario.id))
 assert run.inputs["mode"]=="independent" and run.inputs["calibration_id"] is None
 run_service.compute(db,run.id)
 rob=run.result["robustness"]
 assert rob["mode"]=="independent" and rob["joint"] is None and "独立均匀扰动" in rob["assumption"]

# ---------- 导入解析 ----------

def test_parse_csv_keeps_missing_blank_and_rejects_duplicates():
 rows,batches=parse_csv(csv_of(paired_rows(6,missing={(2,"A","cost")})))
 assert batches==6
 hit=[r for r in rows if r["batch_id"]=="B02" and r["material_id"]=="A"][0]
 assert hit["cost"] is None                              # 缺测留空为None，绝不补零
 dup=paired_rows(6);dup.append(dict(dup[0]))
 with pytest.raises(ValueError):parse_csv(csv_of(dup))
