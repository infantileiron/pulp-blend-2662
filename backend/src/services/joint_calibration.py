import numpy as np
from scipy.stats import spearmanr,norm
from ..constants.enums import PROPERTIES,MEASUREMENT_PROPERTIES,JOINT_MIN_OBS,JOINT_MIN_PAIRS,JOINT_EIGEN_TOLERANCE,JOINT_REPAIR_FLOOR,JOINT_REPAIR_MAX_ADJUST

def dimension_keys(materials,perturb_cost):
 keys=[]
 for m in materials:
  for prop in PROPERTIES:keys.append(m["material_id"]+":"+prop)
  if perturb_cost:keys.append(m["material_id"]+":cost")
 return keys

def active_dimension_keys(materials,perturb_cost):
 """零扰动宽度维变换后为常量，秩相关无定义，不要求校准覆盖。"""
 keys=[]
 for m in materials:
  for prop in PROPERTIES:
   if m[prop+"_width"]>0:keys.append(m["material_id"]+":"+prop)
  if perturb_cost and m["cost_width"]>0:keys.append(m["material_id"]+":cost")
 return keys

def estimate(rows):
 """按检测批号配对估计Spearman秩相关。缺测只按成对完整样本参与，绝不补零；
 常量维度（如零扰动宽度原浆）秩相关无定义，剔除并明示。
 样本不足或相关矩阵非半正定时返回ok=False与原因，调用方不得退化为独立抽样。"""
 series={}
 for row in rows:
  for prop in MEASUREMENT_PROPERTIES:
   if row.get(prop) is None:continue
   series.setdefault(row["material_id"]+":"+prop,{})[row["batch_id"]]=row[prop]
 dropped=[];varying={}
 for key,values in series.items():
  vals=np.array(list(values.values()),dtype=float)
  if vals.std()==0:dropped.append(key)
  else:varying[key]=values
 keys=sorted(varying)
 if len(keys)<2:return {"ok":False,"reason":"非常量有效扰动维度不足2个，无法构成相关结构"+("；已剔除常量维度："+"、".join(dropped) if dropped else ""),"dropped":dropped}
 key_counts={key:len(varying[key]) for key in keys}
 short=[f"{key}仅{n}条" for key,n in key_counts.items() if n<JOINT_MIN_OBS]
 if short:return {"ok":False,"reason":f"有效样本不足（每维至少{JOINT_MIN_OBS}条实测，缺测不补零）："+"、".join(short),"keys":keys,"key_counts":key_counts,"dropped":dropped}
 k=len(keys);matrix=np.eye(k);counts=np.zeros((k,k),dtype=int)
 for i in range(k):
  for j in range(i+1,k):
   common=sorted(set(varying[keys[i]])&set(varying[keys[j]]))
   counts[i,j]=counts[j,i]=len(common)
   if len(common)<JOINT_MIN_PAIRS:return {"ok":False,"reason":f"维度{keys[i]}与{keys[j]}的成对完整样本仅{len(common)}批（至少{JOINT_MIN_PAIRS}批），缺测不补零，无法可靠估计相关","keys":keys,"key_counts":key_counts,"dropped":dropped}
   x=np.array([varying[keys[i]][b] for b in common]);y=np.array([varying[keys[j]][b] for b in common])
   rho=spearmanr(x,y).correlation
   if not np.isfinite(rho):return {"ok":False,"reason":f"维度{keys[i]}与{keys[j]}在成对完整样本交集内为常量，秩相关无定义；请补充覆盖交集的实测","keys":keys,"key_counts":key_counts,"dropped":dropped}
   matrix[i,j]=matrix[j,i]=float(np.clip(rho,-1.,1.))
 min_eigen=float(np.linalg.eigvalsh((matrix+matrix.T)/2).min())
 base={"keys":keys,"key_counts":key_counts,"pair_counts":counts.tolist(),"dropped":dropped}
 if min_eigen>=-JOINT_EIGEN_TOLERANCE:return {"ok":True,"matrix":matrix.round(10).tolist(),"min_eigenvalue":min_eigen,"adjusted":False,**base}
 if min_eigen<JOINT_REPAIR_FLOOR:return {"ok":False,"reason":f"估计的相关矩阵非半正定（最小特征值{min_eigen:.6g}），联合相关结构不可实现；请增加配对样本或核查缺测模式，不以独立抽样冒充联合扰动","min_eigenvalue":min_eigen,**base}
 repaired=nearest_correlation(matrix)
 adjust=float(np.abs(repaired-matrix).max())
 if adjust>JOINT_REPAIR_MAX_ADJUST:return {"ok":False,"reason":f"相关矩阵非半正定（最小特征值{min_eigen:.6g}），最近可实现矩阵需调整{adjust:.4f}，超出诚实披露范围{JOINT_REPAIR_MAX_ADJUST}，判定不可实现；不以独立抽样冒充联合扰动","min_eigenvalue":min_eigen,**base}
 return {"ok":True,"matrix":repaired.round(10).tolist(),"min_eigenvalue":float(np.linalg.eigvalsh((repaired+repaired.T)/2).min()),"adjusted":True,"raw_min_eigenvalue":min_eigen,"max_adjustment":adjust,**base}

def nearest_correlation(a,tol=1e-12,max_iter=300):
 """Higham交替投影到最近相关矩阵（半正定且对角为1）。仅用于小幅不可实现的诚实修复，调整量由调用方披露。"""
 y=(np.asarray(a,dtype=float)+np.asarray(a,dtype=float).T)/2
 ds=np.zeros_like(y)
 for _ in range(max_iter):
  r=y-ds
  vals,vecs=np.linalg.eigh((r+r.T)/2)
  x=(vecs*np.clip(vals,0.,None))@vecs.T
  ds=x-r
  np.fill_diagonal(x,1.)
  if np.abs(x-y).max()<tol:y=x;break
  y=x
 d=np.sqrt(np.clip(np.diag(y),1e-12,None))
 y=y/np.outer(d,d)
 np.fill_diagonal(y,1.)
 return y

def iman_conover(u,target,seed):
 """Iman–Conover：只重排各列次序，使列间Spearman秩相关逼近target。
 每列取值集合不变，因此均匀边际与每维分层严格保留。target可为半正定（含完全正负相关）。"""
 n,k=u.shape
 rng=np.random.default_rng((int(seed),20261115))
 sym=(np.asarray(target,dtype=float)+np.asarray(target,dtype=float).T)/2
 vals,vecs=np.linalg.eigh(sym)
 factor=vecs*np.sqrt(np.clip(vals,0.,None))
 base=norm.ppf((np.arange(n)+.5)/n)
 scores=np.empty((n,k))
 for j in range(k):scores[:,j]=base[rng.permutation(n)]
 cs=np.corrcoef(scores,rowvar=False)
 w_vals,w_vecs=np.linalg.eigh((cs+cs.T)/2)
 inv=np.where(w_vals>1e-12,1./np.sqrt(np.clip(w_vals,1e-12,None)),0.)
 whiten=(w_vecs*np.sqrt(inv))@w_vecs.T
 t=scores@whiten@factor.T
 out=np.empty_like(u)
 for j in range(k):out[np.argsort(t[:,j],kind="stable"),j]=np.sort(u[:,j])
 ranks=np.empty_like(out)
 for j in range(k):ranks[np.argsort(out[:,j],kind="stable"),j]=np.arange(n)
 actual=np.corrcoef(ranks,rowvar=False)
 return out,actual
