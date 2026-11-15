import numpy as np
from ..constants.enums import PROPERTIES,CONSTRAINT_TOLERANCE
from .joint_calibration import dimension_keys,iman_conover

def latin_hypercube(n,d,seed):
 if not isinstance(n,int) or n<2 or not isinstance(d,int) or d<1:raise ValueError("LHS样本数与维数无效")
 rng=np.random.default_rng(seed);u=np.empty((n,d))
 for j in range(d):u[:,j]=(rng.permutation(n)+rng.random(n))/n
 return u

def simulate(materials,shares,spec,n_samples,seed,perturb_cost,joint=None):
 x=np.asarray(shares,dtype=float)
 if len(x)!=len(materials) or not np.isfinite(x).all() or (x<-CONSTRAINT_TOLERANCE).any() or abs(float(x.sum())-1)>CONSTRAINT_TOLERANCE:raise ValueError("固定配方比例无效")
 dimensions=[]
 for m in materials:
  for key in PROPERTIES:dimensions.append({"material_id":m["material_id"],"property":key,"low":m[key]-m[key+"_width"],"high":m[key]+m[key+"_width"]})
  if perturb_cost:dimensions.append({"material_id":m["material_id"],"property":"cost","low":m["cost"]-m["cost_width"],"high":m["cost"]+m["cost_width"]})
 u=latin_hypercube(n_samples,len(dimensions),seed);joint_report=None
 if joint is not None:
  dim_keys=dimension_keys(materials,perturb_cost)
  widths=[]
  for m in materials:
   for key in PROPERTIES:widths.append(m[key+"_width"])
   if perturb_cost:widths.append(m["cost_width"])
  active=[i for i,w in enumerate(widths) if w>0];active_keys=[dim_keys[i] for i in active]
  if len(active)<2:raise ValueError("联合扰动至少需要2个非常量扰动维度")
  missing=[k for k in active_keys if k not in joint["keys"]]
  if missing:raise ValueError("校准未覆盖情景扰动维度："+"、".join(missing[:6]))
  idx=[joint["keys"].index(k) for k in active_keys]
  target=np.asarray(joint["matrix"],dtype=float)[np.ix_(idx,idx)]
  induced,actual=iman_conover(u[:,active],target,seed)
  for pos,column in enumerate(active):u[:,column]=induced[:,pos]
  pairs=np.asarray(joint["pair_counts"],dtype=int)[np.ix_(idx,idx)]
  upper=np.triu_indices(len(active_keys),1);dev=np.abs(actual-target)[upper]
  joint_report={"calibration_id":joint["calibration_id"],"calibration_name":joint["calibration_name"],"source_version":joint["source_version"],"method":"Spearman秩相关+Iman–Conover重排（仅改变各维样本次序，不改变各维取值集合，均匀边际与每维分层严格保留）","keys":active_keys,"constant_keys":[dim_keys[i] for i in range(len(dim_keys)) if i not in active],"target":np.round(target,6).tolist(),"actual":np.round(actual,6).tolist(),"max_abs_deviation":float(dev.max()),"mean_abs_deviation":float(dev.mean()),"pair_counts":pairs.tolist(),"min_pair_n":int(pairs[upper].min()),"key_counts":{k:joint["key_counts"][k] for k in active_keys},"min_eigenvalue":joint["min_eigenvalue"]}
 values={key:np.zeros(n_samples) for key in PROPERTIES};cost=np.zeros(n_samples);column=0
 for i,m in enumerate(materials):
  for key in PROPERTIES:
   lo,hi=m[key]-m[key+"_width"],m[key]+m[key+"_width"]
   values[key]+=x[i]*(lo+(hi-lo)*u[:,column]);column+=1
  if perturb_cost:
   cost+=x[i]*(m["cost"]-m["cost_width"]+2*m["cost_width"]*u[:,column]);column+=1
  else:cost+=x[i]*m["cost"]
 compliant=np.ones(n_samples,dtype=bool)
 for key in PROPERTIES:compliant&=(values[key]>=spec[key+"_min"]-CONSTRAINT_TOLERANCE)&(values[key]<=spec[key+"_max"]+CONSTRAINT_TOLERANCE)
 samples=[{"index":i+1,"cost":float(cost[i]),"compliant":bool(compliant[i]),**{key:float(values[key][i]) for key in PROPERTIES}} for i in range(n_samples)]
 assumption="求得配方固定不变；每原浆属性按检测批号配对实测估计的秩相关联合扰动（Iman–Conover），各维边际仍为声明的独立均匀分布且分层保留。仅模拟线性加权混合；合规率为通过数/样本数，成本区间为模拟分位，不是认证或置信区间。" if joint is not None else "求得配方固定不变；每原浆属性独立均匀扰动，LHS各维分层。仅模拟线性加权混合；合规率为通过数/样本数，成本区间为模拟分位，不是认证或置信区间。"
 return {"n_samples":n_samples,"passed":int(compliant.sum()),"failed":int((~compliant).sum()),"compliance_rate":float(compliant.mean()),"cost_p05":float(np.quantile(cost,.05)),"cost_p50":float(np.quantile(cost,.5)),"cost_p95":float(np.quantile(cost,.95)),"seed":seed,"perturb_cost":perturb_cost,"dimension_count":len(dimensions),"dimensions":dimensions,"samples":samples,"fixed_shares":x.tolist(),"comparison_tolerance":CONSTRAINT_TOLERANCE,"mode":"joint" if joint is not None else "independent","joint":joint_report,"assumption":assumption}
