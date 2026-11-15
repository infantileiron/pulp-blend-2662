import csv,io,math
from ..constants.enums import MEASUREMENT_PROPERTIES,PHYSICAL_BOUNDS
REQUIRED=["batch_id","material_id","strength","whiteness","recycled"]

def parse_csv(text):
 rows=list(csv.DictReader(io.StringIO(text)))
 if not rows or not set(REQUIRED).issubset(rows[0].keys()):raise ValueError("配对实测CSV需包含列："+",".join(REQUIRED)+"，cost列可选")
 if not 4<=len(rows)<=5000:raise ValueError("配对实测记录需在4至5000行之间")
 result=[];seen=set();batches=set()
 for index,row in enumerate(rows,2):
  batch=(row.get("batch_id") or "").strip();ident=(row.get("material_id") or "").strip()
  if not batch or len(batch)>60 or not ident or len(ident)>60:raise ValueError(f"第{index}行检测批号/原浆ID为空或过长")
  if (batch,ident) in seen:raise ValueError(f"第{index}行检测批号{batch}与原浆{ident}重复")
  seen.add((batch,ident));batches.add(batch)
  item={"batch_id":batch,"material_id":ident}
  for key in MEASUREMENT_PROPERTIES:
   cell=row.get(key)
   if cell is None or not str(cell).strip():item[key]=None;continue
   try:value=float(cell)
   except Exception:raise ValueError(f"第{index}行{key}必须为数值或留空（缺测留空，不补零）")
   if not math.isfinite(value):raise ValueError(f"第{index}行{key}必须有限")
   if key=="cost":
    if not 0<value<=1e6:raise ValueError(f"第{index}行成本实测须为正且不超过1e6")
   else:
    lo,hi=PHYSICAL_BOUNDS[key]
    if not lo<=value<=hi:raise ValueError(f"第{index}行{key}实测超出物理范围[{lo},{hi}]")
   item[key]=value
  if all(item[key] is None for key in MEASUREMENT_PROPERTIES):raise ValueError(f"第{index}行全部缺测，无法使用")
  result.append(item)
 if len(batches)<4:raise ValueError("至少需要4个不同检测批号")
 return result,len(batches)
