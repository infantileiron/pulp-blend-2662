import hashlib
from uuid import uuid4
from sqlalchemy import select,update
from fastapi import HTTPException
from ..models.measurement import MeasurementSet
from ..models.calibration import JointCalibration
from .paired_measurements import parse_csv

def create(db,body):
 if db.scalar(select(MeasurementSet).where(MeasurementSet.name==body.name)):raise HTTPException(409,"配对实测记录集名称已存在")
 try:rows,batches=parse_csv(body.csv_text)
 except ValueError as e:raise HTTPException(422,str(e))
 row=MeasurementSet(id=str(uuid4()),name=body.name,version=1,content_hash=hashlib.sha256(body.csv_text.encode()).hexdigest(),rows=rows,batches=batches,description=body.description)
 db.add(row);db.commit();return row

def reimport(db,ident,body):
 """源数据更新：版本号递增，同事务把基于旧版的草稿/已发布校准置为失效。
 任一环节失败整体回滚，保留旧版。"""
 row=db.get(MeasurementSet,ident)
 if row is None:raise HTTPException(404,"记录不存在")
 try:rows,batches=parse_csv(body.csv_text)
 except ValueError as e:raise HTTPException(422,str(e))
 digest=hashlib.sha256(body.csv_text.encode()).hexdigest()
 if digest==row.content_hash:raise HTTPException(409,"源数据内容未变化，无需更新")
 row.rows=rows;row.batches=batches;row.content_hash=digest;row.version+=1
 db.execute(update(JointCalibration).where(JointCalibration.measurement_set_id==ident,JointCalibration.status.in_(["draft","published"])).values(status="stale",reason="配对实测源数据已更新至v"+str(row.version)+"，请重新估计并发布"))
 db.commit();return row
