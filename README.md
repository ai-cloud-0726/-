# 可控持续进化 Python 系统（main + claw）

本项目第二版重点是让“进化闭环”真实成立，而不是仅堆功能。

闭环：**目标管理 → 规划评分 → 执行 → 程序化验证 → 复盘沉淀 → 受控演化（快照/回滚）**。

## 架构

- `main.py`：总控入口（递归、重启、补丁白名单、快照/回滚、历史与复盘、基准测试）
- `claw.py`：多轮执行核心（每轮规划、执行、程序化验证、评估、改进）
- `system/`：模块化子系统
  - `goal_manager.py`：目标状态机（主目标/子目标/阻塞点/下一步）
  - `planner.py`：策略候选+评分器
  - `executor.py`：执行与权限分级、危险命令拦截
  - `verifier.py`：程序化验证器（返回码/产物/JSON 等）
  - `evaluator.py`：结果评估（结合验证器）
  - `reflector.py`：任务复盘记录
  - `evolver.py`：版本快照与回滚
  - `improver.py`：能力不足判定与补丁请求
  - `memory.py`：状态/目标/错误/补丁/历史/复盘/基准/日志
  - `model.py`：统一模型调用封装
  - `prompts.py`：提示词管理与版本化
  - `registry.py`：能力注册、质量统计、自动淘汰归档
  - `types.py`：状态与数据结构定义

## 配置

- `config.json`
  - 路径配置（runtime/logs/history/temp/abilities/prompts/versions/snapshots）
  - 控制参数（最大步数、最大递归、最大重启、最大失败尝试等）
  - 危险命令黑名单
  - 权限分级（L1-L4，默认 L2）
  - 自修改补丁白名单
- `models.json`：大模型完整配置（active_profile、profiles、provider、endpoint、headers、key 环境变量、重试超时、模型路径/trace 路径）

## 关键数据文件

- `runtime/state.json`：运行态
- `runtime/goal_state.json`：目标状态机
- `runtime/error_memory.json`：错误记忆
- `runtime/patch_queue.json`：补丁队列
- `runtime/ability_registry.json`：能力注册
- `runtime/archived_abilities.json`：淘汰归档能力
- `runtime/prompt_metadata.json`：提示词元数据
- `runtime/dashboard.json`：运行仪表盘（迭代次数、token 估算、轮数、错误数等）
- `versions/version_meta.json`：版本元数据
- `history/tasks.json`：任务历史
- `history/retrospectives.json`：任务复盘
- `history/benchmarks.json`：基准任务集
- `logs/run.log`：运行日志
- `logs/debug.log`：调试日志

## 运行

```bash
python main.py
python main.py "你的目标"
python main.py --benchmark
python main.py --dashboard

# 对话模式命令
# 直接输入目标: 执行任务
# :resume <goal> : 基于历史状态续跑
# :benchmark     : 运行基准
# :dashboard     : 查看仪表盘
# :exit          : 退出
```

## 三类扩展能力

1. **受控自修改**：通过补丁请求，统一由 `main` 在白名单内应用。
2. **通用能力沉淀**：能力代码写入固定目录并登记元数据与质量统计。
3. **临时代码实验**：临时代码仅写入 `temp/`。

## 设计原则

- 受控持续进化，不做无约束自改。
- 程序化验证优先，模型语义判断补充。
- 每次演化可审计、可回滚、可基准对比。


## 一致性评估

- 已重新审查当前实现与需求：保留主控/执行分离、递归重启约束、状态续传、错误记忆、补丁白名单与日志分层。
- 新增仪表盘用于持续观察 claw 迭代次数、任务轮数、token 估算、错误数、能力规模等运行指标。
