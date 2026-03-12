# Main + Claw 可控进化执行系统

该项目实现了一个由 `main`（总控）与 `claw`（执行核心）组成的 Python 系统，支持递归、重启、状态续传、错误记忆、补丁队列、能力沉淀、提示词版本化和完整日志/调试记录。

## 目录结构

- `main.py`: 总控入口，负责生命周期管理与补丁统一处理。
- `claw.py`: 多轮执行核心，含规划/执行/评估/改进闭环。
- `agent_system/`
  - `core`: 数据结构与状态枚举。
  - `planner`: 下一步动作规划。
  - `executor`: 动作执行与命令黑名单。
  - `evaluator`: 目标/步骤对齐检查与结果评估。
  - `improver`: 失败改进、扩展策略、补丁申请。
  - `memory`: 状态、历史、错误、日志、调试写入。
  - `model`: 统一模型调用入口。
  - `prompts`: 提示词加载与受控版本更新。
  - `registry`: 通用能力登记与复用。
- `config.json`: 系统配置（路径、限制、黑名单、补丁白名单）。
- `models.json`: 模型配置。
- `data/`: 运行时目录（日志、调试、状态、补丁、能力、提示词、临时代码）。

## 运行

```bash
python main.py "你的任务目标"
```

## 核心约束落实

- 最大递归次数：`config.json -> limits.max_recursions`
- 最大重启次数：`config.json -> limits.max_restarts`
- 单任务最大补丁数：`config.json -> limits.max_patch_per_task`
- 单任务最大失败尝试：`config.json -> limits.max_fail_attempts_per_task`
- 同类错误重复上限：`config.json -> limits.max_same_error_repeats`
- 危险命令黑名单：`config.json -> dangerous_commands_blacklist`
- 自改白名单：`config.json -> patch.allowed_files`

## 输出与状态

- 运行日志：`data/logs/*.log.jsonl`
- 调试日志：`data/debug/*.debug.jsonl`
- 运行状态：`data/state/*_runtime_state.json`
- 错误记忆：`data/state/*_error_memory.json`
- 补丁队列：`data/patches/*_patch_queue.json`
- 历史任务：`data/history/execution_history.jsonl`
- 能力注册：`data/abilities/ability_registry.json`
- 提示词元数据：`data/prompts/prompt_meta.json`
