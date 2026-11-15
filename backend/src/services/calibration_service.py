from uuid import uuid4
from sqlalchemy import select,update
from fastapi import HTTPException
from ..models.measurement import MeasurementSet
from ..models.calibration import JointCalibration
from .joint_calibration import estimate

ASSUMPTION="原浆检测同涨同跌，按检测批号配对估计Spearman秩相关；试算以Iman–Conover在保留均匀边际与每维分层的前提下诱导联合扰动。秩相关不代表因果；缺测按成对完整样本处理，不补零；模拟结论不构成工业质量认证。"

def note_for(est):
 """把估计诊断写成可审计说明：非半正定修复、常量维度剔除都要明示。"""
 if not est["ok"]:return est["reason"]
 notes=[]
 if est.get("adjusted"):notes.append(f"原始估计非半正定（最小特征值{est['raw_min_eigenvalue']:.6g}），已投影至最近可实现相关矩阵，最大单项调整{est['max_adjustment']:.4f}；底稿目标相关性以修复后矩阵为准")
 if est.get("dropped"):notes.append("常量维度未参与相关估计（秩相关无定义）："+"、".join(est["dropped"]))
 return "；".join(notes)

def require_usable(db,cal):
 """试算创建/情景选择前的校准闸门：仅已发布且源数据版本未漂移的校准可用。"""
 if cal is None:raise HTTPException(422,"联合校准不存在")
 if cal.status=="invalid":raise HTTPException(409,"校准估计失败，不可使用："+cal.reason)
 if cal.status=="draft":raise HTTPException(409,"校准仍为草稿，发布后才可供情景选择")
 if cal.status=="stale":raise HTTPException(409,"配对实测源数据已更新，该校准已失效，请重新估计并发布；已完成试算不受影响")
 ms=db.get(MeasurementSet,cal.measurement_set_id)
 if ms is None or cal.source_version!=ms.version:raise HTTPException(409,"配对实测源数据版本已漂移，该校准不可用于新试算；已完成试算不受影响")
 return cal

def create(db,body):
 ms=db.get(MeasurementSet,body.measurement_set_id)
 if ms is None:raise HTTPException(422,"配对实测记录集不存在")
 if db.scalar(select(JointCalibration).where(JointCalibration.name==body.name)):raise HTTPException(409,"校准名称已存在")
 est=estimate(ms.rows)
 row=JointCalibration(id=str(uuid4()),name=body.name,measurement_set_id=ms.id,source_version=ms.version,status="draft" if est["ok"] else "invalid",reason=note_for(est),keys=est.get("keys",[]),matrix=est.get("matrix",[]),pair_counts=est.get("pair_counts",[]),key_counts=est.get("key_counts",{}),min_eigenvalue=est.get("min_eigenvalue"),method="Spearman秩相关（按检测批号成对完整样本，缺测不补零）" if est["ok"] else "",assumption=ASSUMPTION if est["ok"] else "")
 db.add(row);db.commit();return row

def publish(db,ident):
 """草稿→发布的原子迁移：条件更新保证并发发布只有一个成功，失败者保留旧版状态。"""
 fresh=select(MeasurementSet.version).where(MeasurementSet.id==JointCalibration.measurement_set_id).scalar_subquery()
 result=db.execute(update(JointCalibration).where(JointCalibration.id==ident,JointCalibration.status=="draft",JointCalibration.source_version==fresh).values(status="published"))
 if result.rowcount==1:
  db.commit();return db.get(JointCalibration,ident)
 db.rollback()
 row=db.get(JointCalibration,ident)
 if row is None:raise HTTPException(404,"记录不存在")
 if row.status=="published":raise HTTPException(409,"该校准已发布（并发发布仅一个生效），旧版状态保持不变")
 if row.status=="invalid":raise HTTPException(409,"估计失败的校准不可发布："+row.reason)
 if row.status=="stale":raise HTTPException(409,"配对实测源数据已更新，请基于新版本重新估计")
 raise HTTPException(409,"校准状态不允许发布")
