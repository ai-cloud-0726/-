# 学迹智评接口设计说明书

## 1. 基本约定

- Base URL：`/api/v1`
- 协议：HTTPS + JSON
- 认证：`Authorization: Bearer <access_token>`
- 时间：ISO 8601 UTC
- 分页：`page`、`page_size`，默认 1/20
- 幂等：上传、提交、报告生成支持 `Idempotency-Key`

统一响应：

```json
{
  "success": true,
  "data": {},
  "error": null,
  "request_id": "uuid"
}
```

## 2. 认证

### POST `/auth/login`

```json
{"account":"parent@example.com","password":"******"}
```

返回 access_token、refresh_token、role、user。

### POST `/auth/refresh`

轮换 refresh token。

### POST `/auth/logout`

注销当前设备会话。

## 3. 家庭与学生

### GET `/families/me`
获取当前家庭及成员。

### POST `/students`
家长创建学生。

```json
{
  "nickname":"林小雨",
  "birth_month":"2015-05-01",
  "region_code":"440100",
  "school_system":"6-3"
}
```

### GET `/students/{student_id}`
获取学生档案，必须校验绑定关系。

### PATCH `/students/{student_id}`
修改非历史化基础资料。

## 4. 学年与教材

### POST `/students/{student_id}/terms`
创建学生学期配置。

### POST `/students/{student_id}/subjects`
配置分科教材和能力年级。

```json
{
  "term_id":"uuid",
  "subject_code":"math",
  "textbook_id":"uuid",
  "ability_grade":4.8,
  "current_chapter_id":"uuid",
  "progress_source":"parent"
}
```

### GET `/catalog/textbooks`
按科目、年级、地区、修订年份筛选教材。

### GET `/catalog/textbooks/{id}/tree`
获取单元—章节—课时—知识点树。

## 5. 资料上传与 OCR

### POST `/students/{student_id}/documents`

multipart/form-data：

- file
- document_type
- captured_at（可选）

返回 `document_id` 和状态。

### GET `/documents/{document_id}`
获取处理状态、原图临时地址和识别结果。

### POST `/documents/{document_id}/retry`
重试失败 OCR。

### POST `/documents/{document_id}/confirm`
家长确认结构化字段。

```json
{
  "document_type":"score",
  "fields":{
    "subject_code":"math",
    "exam_name":"第六单元测验",
    "exam_date":"2026-07-14",
    "score":86,
    "full_score":100,
    "class_average":81
  },
  "corrections":[{"field":"score","before":"8G","after":"86"}]
}
```

## 6. 成绩与评语

### GET `/students/{student_id}/scores`
支持科目和日期筛选。

### GET `/students/{student_id}/comments`
返回原文、结构化标签、证据和版本。

### PATCH `/scores/{score_id}`
正式成绩修订，必须提供 reason 并生成新版本。

## 7. 题库

### GET `/questions`
管理员按学科、教材、知识点、状态筛选。

### POST `/questions`
创建题目草稿。

### POST `/questions/{id}/review`
提交审核或审核通过。

### POST `/questions/{id}/publish`
发布题目，仅管理员。

### GET `/admin/question-bank/coverage`
查看教材知识点覆盖率。

## 8. 练习与评测

### POST `/students/{student_id}/practice-sessions`

```json
{
  "type":"daily_practice",
  "subject_code":"math",
  "knowledge_point_ids":["uuid"],
  "planned_minutes":15,
  "question_count":4
}
```

### GET `/practice-sessions/{id}`
返回题目快照，不返回标准答案。

### POST `/practice-sessions/{id}/items/{item_id}/answers`

```json
{
  "attempt_no":1,
  "answer":{"option":"B"},
  "duration_seconds":42,
  "hint_count":0
}
```

返回是否正确、得分、下一层提示或解析权限。

### POST `/practice-sessions/{id}/submit`
结束练习并触发掌握度更新。

## 9. 错题与掌握度

### GET `/students/{student_id}/wrong-questions`
按状态、科目和知识点筛选。

### POST `/wrong-questions/{id}/retest`
生成原题/同类题/变式题复测任务。

### GET `/students/{student_id}/mastery`
返回知识点得分、状态、证据量和更新时间。

## 10. 学习任务

### GET `/students/{student_id}/tasks`
学生或绑定家长查看任务。

### POST `/students/{student_id}/tasks`
家长推送任务。

### PATCH `/tasks/{id}`
更新任务状态或设置自动顺延。

## 11. AI 报告

### POST `/students/{student_id}/reports`

```json
{
  "report_type":"parent_weekly",
  "period_start":"2026-07-08",
  "period_end":"2026-07-14"
}
```

返回异步 job_id。

### GET `/reports/{id}`
返回状态、结构化报告、证据和数据不足项。

### POST `/reports/{id}/regenerate`
只允许数据变化或管理员质量处理时重新生成。

## 12. 打印

### POST `/print-jobs`
支持 practice、wrong_book、knowledge_cards、student_report、parent_report。

### GET `/print-jobs/{id}`
完成后返回短期 PDF 下载地址。

## 13. 后台配置

- `/admin/users`
- `/admin/textbooks`
- `/admin/knowledge-points`
- `/admin/questions`
- `/admin/ai-providers`
- `/admin/ocr-providers`
- `/admin/report-templates`
- `/admin/audit-logs`
- `/admin/system-health`

## 14. HTTP 状态

- 200：成功
- 201：创建成功
- 202：异步任务已接收
- 400：参数或业务状态错误
- 401：未认证
- 403：无权限
- 404：资源不存在
- 409：重复提交/状态冲突
- 413：文件过大
- 422：字段校验失败
- 429：频率或额度限制
- 500：内部错误
- 503：外部 AI/OCR 暂不可用
