# 岑岳纸业 · 原浆配比稳健试算

在明确的模拟线性混合假设下，求名义最小成本原浆配方，再固定比例做拉丁超立方扰动试算，报告质量通过数和成本分位。面向岑岳纸业16人配方组，不提供工业质量认证。

## 场景与数据链路

原流程用 `cenyue_pulp_202611.csv` 的检测值和报价在Excel手调比例。三个痛点是质量界限相互冲突、名义低成本配方对波动脆弱、成本/属性扰动没有统一口径。上游为模拟原浆中心属性、报价、供给上下限与误差宽度；本项目替代名义配比求解和固定配方评价；下游由配方组对照实验与真实工艺复核。

原浆检测常同涨同跌，独立扰动会低估配方风险。为此支持导入按检测批号配对的多原浆实测记录，估计联合扰动校准：Spearman秩相关按成对完整样本计算，缺测留空不补零；试算用Iman–Conover重排在保留均匀边际与每维分层的前提下诱导目标秩相关。样本不足或相关矩阵非半正定时写明原因（轻微不可实现投影至最近相关矩阵并披露调整量），绝不以独立抽样冒充联合扰动。

八实体贯穿数据库、Python Model/Schema/Service/Controller/Route、Vue API/Store/页面：PulpDataset、QualitySpec、BlendScenario、BlendRun、FormulaReview、Report、MeasurementSet、JointCalibration。七业务页为总览、原浆检测、质量窗口、试算情景、联合校准、运行底稿、配方归档，另有管理员审计。

## 启动与技术

```sh
cp .env.example .env
docker compose up -d --build --wait
docker compose exec -T backend python -m scripts.seed_demo
```

前端 http://localhost:18225 ，API文档 http://localhost:19225/docs ，MySQL宿主17725。Nginx把 `/api/` 去前缀转发给Python，开发代理同口径；`/health`实际检查数据库及Redis。

| 层 | 版本与实现 |
|---|---|
| 前端 | Vue3.5.13、TypeScript5.7.2、Vite6.0.5、vue-tsc2.2.0 |
| 依赖 | 精确复用已验Vue锁及版本，仅JSON根工程名变化，npm ci |
| 后端 | Python3.12、FastAPI0.115.6、SQLAlchemy2.0.36 |
| 数值 | NumPy2.2.1、SciPy1.14.1 linprog/HiGHS |
| 存储 | MySQL8.4 LTS、Redis7.4，六个质量界限列均DOUBLE |
| 后台 | 独立worker、Redis队列、MySQL保存结果与不可变报告 |
| 网关 | Nginx1.28，SPA回落，健康检查127.0.0.1 |

五服务恰好frontend/backend/worker/db/redis，全部healthcheck，数据库/Redis/共享产物具名卷。清理 `docker compose down -v --remove-orphans`；保留数据时省略 `-v`。

结构：`backend/src/{models,schemas,services,controllers,routes}`按八实体分层，`services/materials.py`校验原浆CSV，`paired_measurements.py`校验配对实测CSV，`linear_blend.py`求名义配方，`lhs_robustness.py`构造LHS并评价固定配方，`joint_calibration.py`估计秩相关并做Iman–Conover诱导；`config,utils,middlewares`提供配置/数据库/认证/队列/审计/错误。种子 `backend/scripts/seed_demo.py`；`migrations/001_schema.sql`说明新库基线，`002_joint_calibration.sql`说明联合校准加列，实际启动以元数据建表。前端 `src/{api,stores,types,constants,hooks,utils,router,pages}`；RecipeBars、QualityTable、SampleCloud用于总览/结果/归档。测试、日志、截图在批次外层 `test-artifacts/`，不放本源码目录；联合校准验证在 `test-artifacts/joint-calibration`。

本地开发：安装requirements并设置可用DATABASE_URL/REDIS_URL，从backend运行 `uvicorn src.main:app --reload`，另起 `python -m src.worker`；前端 `npm ci && npm run dev`，构建 `npm run build`。默认OpenBLAS/OMP线程1，避免小型试算占满主机。

环境变量COMPOSE_PROJECT_NAME、FRONTEND_PORT、BACKEND_PORT、DB_PORT、JWT_SECRET、SEED_DEMO；DATABASE_URL/REDIS_URL由Compose内部提供。`.env`忽略，演示密钥和数据库口令仅供本地模拟，部署使用独立配置。

## 账号与权限

统一演示密码 `PulpDemo2026!`，PBKDF2-SHA256独立salt口令摘要，JWT八小时有效。

| 账号 / 角色 | 页面与动作 | 后端权限 |
|---|---|---|
| admin@pulp.demo / admin | 配方复核、批准归档、审计 | 全部分析写入与批准归档 |
| analyst@pulp.demo / analyst | 原浆/规格/情景、计算、提审 | 不能批准或归档 |
| viewer@pulp.demo / viewer | 阅读、下载批准配方和扰动样本 | 写入403 |

无登录401；错角色403；不可行/失败运行不能提审409；未批准不能归档409。同一已审复核重复创建报告返回同一快照，不覆盖原结果。审计保留账号、路径与响应码，不写密码、Token和上传正文。

共享枚举：Role/RunStatus及PROPERTIES在 `backend/src/constants/enums.py`；roles/runStatuses/properties与标签在 `frontend/src/constants/enums.ts`。后端共享CONSTRAINT_TOLERANCE同在constants/enums.py；前端展示服务端返回的数值，不另行计算统计量。

## 输入与物理口径

每批2至20种原浆，CSV列：

`material_id,name,cost,min_share,max_share,strength,whiteness,recycled,strength_width,whiteness_width,recycled_width,cost_width`

cost为元/吨，正且≤1e6；min_share/max_share为0至1的比例且下界≤上界。强度为0至100的**模拟指数**，白度为0至100%，回收纤维率为0至1。每个width为对应单位的非负±幅度，中心±幅度必须完整落在物理范围，成本下界严格正。不会截断抽样值来掩盖非法区间。重复ID、缺失/非有限数、非法区间拒绝；总供给或质量冲突留给求解器返回不可行。

规格六个上下界必须有序且在上述物理范围。每个情景20至2000个LHS样本、非负整数seed，成本扰动开关独立保存；`calibration_id`可空，空即明确声明的独立均匀扰动。

配对实测CSV列：`batch_id,material_id,strength,whiteness,recycled[,cost]`。同一检测批号下各原浆实测成行配对；缺测留空，估计时按成对完整样本计算，绝不补零。每维至少8条实测、每对维度至少6批交集；常量维度（如零扰动宽度原浆）秩相关无定义，剔除并明示。估计失败（样本不足/相关矩阵非半正定且不可诚实修复）的校准保存为invalid并写明原因，不能发布，也不退化为独立抽样。

## 校准生命周期与并发口径

校准从草稿发布后供情景选择；发布为条件更新的原子迁移，并发发布只有一个生效，失败者409且旧版状态不变。源数据reimport使版本号递增，同事务把基于旧版的草稿/已发布校准置为stale并拒绝新试算与发布；内容未变化的reimport拒绝，失败保留旧版。试算创建时把情景、原浆批次、质量窗口、校准及其源版本成套冻结进运行记录，并发发布/更新下不会拼出混合版本；已完成与已排队结果仍可回读复算。底稿展示目标与实际Spearman秩相关、每对有效样本数、最小特征值与修复披露。

## 两个真实Python算法

名义LP为：

`min Σ cost_i*x_i`，约束 `Σx_i=1`、`supply_min_i≤x_i≤supply_max_i`、每属性 `quality_min≤Σproperty_i*x_i≤quality_max`。

使用SciPy linprog的HiGHS求解，保存配方、成本、质量值、质量/供给约束余量；可有多个最优解时保存求解器返回的一个。不可行返回状态infeasible、shares为空、成本null、模拟结果null，不伪造配方。其他数值失败明确failed。

LP结果核验和LHS质量判断**共用绝对容差1e-7**：质量属性以各自单位比较，下界减容差/上界加容差；比例和与供给界限以比例单位比较。物理样本值不因此修改。容差写入结果、配方CSV及扰动样本CSV的 `quality_comparison_tolerance`。这是数值边界处理，不是工业质量容差或追加质量保证。

LHS每维u_j=(该维随机排列的0..N−1 + 独立U[0,1)抖动)/N，保证每维每个1/N区间恰一个样本；seed固定可复现。每原浆3个属性潜在维度，成本开启再加每原浆1维，即D=3M或4M。零宽度维仍有分层潜在u，但变换后是真正常量。

选择已发布联合校准时，先按上式生成独立LHS，再用Iman–Conover按校准的Spearman目标矩阵只重排各维次序诱导秩相关：每列取值集合不变，均匀边际与每维分层严格保留；目标矩阵可半正定（含完全正负相关），零宽度常量维不参与诱导。底稿同时给出目标与样本实际秩相关矩阵及最大/平均绝对偏差，不掩饰诱导误差。

将每维映射到该原浆属性的 `[center−width,center+width]` 独立均匀区间，始终使用**名义LP求得的同一组x**加权重新评价；不在样本中重新优化。成本开启按同类独立均匀区间扰动，关闭则所有样本成本固定名义值。所有三属性上下界均满足数值比较口径才计通过，报告通过数/N、失败数、成本5/50/95分位及每样本值。

强度、白度、回收率线性混合只是此模拟的声明假设；真实纸业可能存在非线性与相关误差。本项目不处理这些工艺效应。模拟分位不是置信区间，样本通过率不是实际质量认证或保证概率。

## 演示工作日

Seed包含8种原浆、价格/供给/三属性及误差宽度，默认强度≥70、白度≥80%、回收纤维率≥25%，400个样本，seed20261112，成本扰动开启。

1. 09:00 核查 `cenyue_pulp_202611.csv` 八原浆的报价、检测单位与供给比例。
2. 09:05 复核各属性中心±幅度都在物理范围，不将回收率25%写成25。
3. 09:10 保存三属性的质量上下界，检查冲突是否有实际依据。
4. 09:14 建立400样本/seed20261112情景，明确成本也扰动。
5. 09:18 送Redisworker，求一个名义低成本配方并核查活跃约束。
6. 09:24 查看固定配方LHS通过数与失败样本，对照成本分位与质量余量。
7. 09:30 分析师提交配方复核，管理员批准假设与结论边界。
8. 09:36 下载配方CSV和完整扰动样本CSV，保留相同的比例与比较容差。

自然键种子幂等；重复执行不覆盖用户修改说明。

## 已知差异

MySQL采用8.4 LTS而非8.0；Redis列表无worker崩溃自动重投/取消；新库建表无存量版本化迁移回滚；实体列表最多200条。仅模拟有限CSV原浆和独立均匀误差，没有真实供应商接口、工厂配方下发、非线性混合、相关误差或真实质量认证。Google Fonts断网时回退字体。

MIT License。真实检查见批次 `test-artifacts/gb-2306/TESTING.md`。
