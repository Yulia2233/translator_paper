# 问题队列约定

规范文件为资料库根目录 `问题标注.json`：

```json
{"schema_version":1,"questions":[{"id":"unique-id","paper_id":"paper-folder","source_sha256":"PDF SHA256","page":8,"section":"原文第 8 页","quote":"所选文本","question":"用户问题","created_at":"2026-10-23T06:00:00Z","status":"pending","answer":null}]}
```

`page` 在导读中为 null。答案是纯文本，填写 PDF 页码和图表证据；回答后设 status=answered、添加 answered_at。前端使用 textContent 显示问题与答案，不执行输入 HTML。每次刷新从本地服务读取最新答案。提交按 ID 幂等，已有答案不被重复提交覆盖。服务不提供自动推理，也不向外部服务器传输论文。

导出文件沿用同一结构，导入时先验证字段、来源指纹、论文目录路径及页码范围，再按 ID 合并到规范队列。未知论文、不同指纹或同 ID 不同正文不自动合并。不要以重建资料库为由清空问题文件。

服务为当前用户的本地阅读辅助进程，仅绑定回环地址，校验 Host／Origin 与页面获取的提交 token，限制提交大小。不要把服务发布到公网。关闭进程后文件与离线浏览器草稿保留。
