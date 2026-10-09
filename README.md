# Agate Sales Agent · 独立产品 1.0

五个 Agent 的独立可运行应用：Research → Validation → Scoring → Sales，以及每轮先运行的 Follow-up。包含 Web 工作台、SQLite 数据库、人工审批、IMAP/SMTP 邮箱连接和每日定时任务。**不依赖 ChatGPT Work 会话或原仓库飞书服务。**

默认离线演示，使用虚构数据；真实模式连接你自己的 OpenAI API 与邮箱。上传代码不等于线上托管、真实 API 验证或邮箱已授权。

## 3分钟启动

需要 Linux/macOS Python 3.11+，无第三方 Python 包。Windows 使用 Docker。

```bash
git clone https://github.com/whitewys-coder/Sales-Intelligence.git
cd Sales-Intelligence
sh start.sh
```

首次生成权限600的私人 `.env`。打开该文件，复制 `APP_TOKEN`，访问 **http://127.0.0.1:8080** 并登录，点击“运行五个 Agent”。演示模式会生成一个明确标记的虚构账户与草稿；重复运行不重复新增，发送按钮禁用。

## 五个 Agent

|Agent|真实实现|输出|
|---|---|---|
|Research|OpenAI Responses API + web_search，限定范围、数量及历史排除|候选账户和可点击检索来源|
|Validation|第二次独立联网核验，再结构化抽取；检查来源是否在工具检索结果中、官方信号日期、公开邮箱、集团证据|证据、验证缺口、资格门槛|
|Scoring|Python确定性规则，25+20+15+15+10+10+5=100|逐项得分；不绕过验证门槛|
|Sales|基于验证账户起草；人工审核、版本哈希审批、SMTP发送|待审批草稿与发送审计|
|Follow-up|IMAP同步发送历史和收件箱，按邮箱/引用关联，模型分类回复，冻结拒绝/退信|账户状态、中文摘要、建议下一步|

这是五个独立职责模块，由一个持久应用串行编排；不是五个独立服务器。Scoring故意不依赖LLM，保证同一输入产生一致评分。

## 切换真实运行

编辑 `.env` 后重启：

```dotenv
APP_MODE=live
OPENAI_API_KEY=你的API密钥
OPENAI_MODEL=你的账号可用且支持Responses与web_search及结构化输出的模型ID
SENDER_NAME=你的英文姓名
SENDER_EMAIL=你的发件邮箱
MAIL_USER=邮箱登录名
MAIL_PASSWORD=邮箱应用专用密码
SCHEDULE_ENABLED=true
```

- `APP_TOKEN` 使用随机值，不能保留示例占位符；`python3 -c "import secrets; print(secrets.token_urlsafe(32))"` 可生成。
- Gmail默认 `imap.gmail.com` 和 `smtp.gmail.com`。使用支持IMAP/SMTP的应用专用密码；是否可用取决于账号安全政策。当前版本**未实现Google OAuth登录**。ChatGPT里的Gmail授权不会自动传入本产品。
- 在邮箱中确认 `IMAP_SENT_FOLDER`，默认 `[Gmail]/Sent Mail`；本地化或企业邮箱需设置真实名称。`IMAP_INBOX_FOLDER=INBOX`。仅这两个文件夹被扫描，不含已归档/垃圾箱；需要专用销售邮箱或额外人工历史核对。
- 发送历史完整扫描用于查重，收件箱也完整扫描。每个文件夹超过 `MAIL_SCAN_LIMIT`（默认1000）或单封邮件超过5MB时**整轮同步失败且禁止发送**，可提高数量限制。不是无限规模邮箱系统。
- 每轮最多研究 `MAX_ACCOUNTS`（1–10，默认5）个候选；并不保证有合格新线索。
- 真实运行会向OpenAI发送研究信息以及相关来信摘要所需的正文；API消耗由你的账号承担。
- `data/demo.sqlite3` 与 `data/live.sqlite3` 隔离，演示账户无法混入真实发送。

## 日常使用

1. 保存国家、行业与企业画像组成的扫描范围；固定排除与证据规则仍然生效。
2. 点击运行，或开启定时后保持服务在线；日志显示各阶段状态，失败不标记成功。
3. 进入账户详情，核对原始来源、集团关系、联系人和邮件地址；模型判断仍需人工确认。
4. 编辑草稿，保存后勾选“我已核实来源、收件人与正文”，批准当前版本。
5. 再点击发送并确认。后台重新同步邮箱，阻止已有联系、回复、拒绝、退信和重复发送。
6. Follow-up在下一轮更新已关联回复；输出下一步建议，**不自动发跟进信或安排会议**。
7. 👍/👎与理由保存至数据库；本版不自动训练或调整权重。

审批绑定收件人、主题及正文哈希；任何正文修改都会撤销批准。收件人由验证结果锁定，UI不能任意替换。邮件附件、抄送、多人审批与回复邮件编辑尚未实现。

SMTP接受不等于投递成功。网络异常导致结果不确定时状态为 `unknown`，重启前的 `sending` 也转为 `unknown`；系统不重试。管理员必须先在邮箱核对Message-ID并人工处理，当前没有一键重发入口。

## Docker部署

先复制 `.env.example` 为 `.env` 并填写随机APP_TOKEN及所需配置，再执行：

```bash
docker compose up --build -d
docker compose logs -f
```

数据存入 `sales-agent-data` 持久卷。默认只绑定宿主机127.0.0.1:8080；远程访问使用SSH隧道或配置HTTPS反向代理与访问控制。内置HTTP服务适合单用户小规模部署，不是多租户生产SaaS。

`SCHEDULE_ENABLED=true` 后按 `APP_TIMEZONE=Asia/Shanghai`、`SCHEDULE_HOUR=9` 运行。每20秒检查一次，到点后的首次检查执行。宕机后当日9点后启动会补执行当天一次；不会补跑历史所有日期。同一天失败任务不无限自动重试，可手工重新运行。手动运行与定时运行可能分别发生，账户/邮件仍通过去重控制。

同一DATA_DIR只允许一个服务进程；勿开多个副本共享SQLite。正在运行的任务或发送期间，新任务/修改会等待或被拒绝。备份时先停止服务，再备份整个data目录或Docker卷；恢复至相同版本后启动。

## API

除页面资源与 `/health` 外，所有请求须带 `Authorization: Bearer <APP_TOKEN>`；不使用浏览器持久存储保存Token。

|方法|路径|用途|
|---|---|---|
|GET|`/api/state`|账户、草稿、运行、日志与非敏感配置|
|GET|`/api/export`|导出私人运行数据（勿提交到公开仓库）|
|POST|`/api/run`|`{}` 启动本轮|
|POST|`/api/scope`|`{"scope":"..."}` 保存范围|
|POST|`/api/drafts/edit`|`id, subject, body` 修改并撤销批准|
|POST|`/api/drafts/approve`|`id, hash, evidence_reviewed:true` 批准当前内容|
|POST|`/api/drafts/send`|`id` 发送已批准草稿|
|POST|`/api/feedback`|`id, valid:boolean, reason` 人工反馈|

## 测试

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖离线全流程、演示/真实数据库隔离、重复账户、来源缺失、固定评分、审批失效、历史联系抑制、退订冻结、发送幂等、SMTP不确定状态以及重启后的定时幂等。真实API/邮箱必须用自己的凭证完成部署验收；本次交付未发送真实邮件，也未声称实测外部付费API或Docker镜像构建。

## 已知边界

- 来源真实性与集团关系由联网模型辅助判断；检索URL检查不能证明页面每句话正确，人工证据审核是发送前必要步骤。同稿不同域名不能仅靠域名数证明独立性。
- 集团去重依赖证据提取的规范域名；历史邮箱只能确定域名，历史子公司需要人工核对集团关系。
- HTML-only邮件正文暂不抽取；会记录邮件头，分类证据不足时保持unknown。只保留纯文本前16000字符用于分类。
- 新发邮件的引用链可关联转交回复；历史账户主要按精确邮箱关联。不能可靠识别未引用原线程的新联系人来信。
- 没有自主爬虫集群、CRM/飞书同步、多用户权限、自动跟进群发或承诺准确率；原Work任务与此产品互不自动同步。开始真实运行前避免两边同时开发相同账户。
- 数据不含现有客户、邮件正文、私人工作流ID或任何凭证。原仓库飞书代码保持独立。

## 参考接口

- [OpenAI Responses Web Search](https://developers.openai.com/api/docs/guides/tools-web-search)
- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)

## LeadContact 邮箱接入（2026-10-09）

已实现正式域名 API 的余额、高级人员筛选、邮箱查询；无电话查询及自动发送功能。
设置 `LEADCONTACT_ENABLED=true`、`LEADCONTACT_API_KEY`，重启服务后在 live 管线中启用。
`LEADCONTACT_MAX_EMAILS=3` 为每轮上限（0–3）；默认关闭，不因更新代码自动消耗积分。
只为独立验证阶段取得 LinkedIn 人员来源、通过业务匹配且未重复的账户补全；
结果存入账户 `leadcontact`，在原有详情中展示，不改变原邮箱、验证资格或发送审批。
供应商 valid 标记不代表邮件必然送达。缺少公共邮箱证据的账户仍需后续核验。

无需 OpenAI 或邮箱配置即可独立测试：
```bash
python3 -m sales_agent.leadcontact credits
python3 -m sales_agent.leadcontact search --keyword Montageautomatisierung --output private/candidates.json
python3 -m sales_agent.leadcontact email --profile-url 'https://www.linkedin.com/in/VERIFIED_PERSON' --output private/email.json
```
将密钥配置在本机 `.env` 或托管环境 Secret；不要提交密钥、查询结果或联系人信息。
搜索可能收费且文档未明确价格；2026-10-09 一次返回7人的查询实测消耗35积分，
这不是后续查询的固定价格保证。邮箱文档价格10积分/次；每次查询前检查余额。
查询错误不自动重试，需先核对余额。运行全套 Agent 仍需要原 OpenAI/邮箱配置。
代码更新不表示已有服务器已重启或定时任务已启用。
