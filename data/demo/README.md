# Demo Data

存放虚构企业“星云科技有限公司”的合成演示数据，包括角色、资源、Security Contract、知识文档和 Mock Tool 数据。

演示数据应能稳定复现安全配置与错误配置，不通过运行前手工篡改来制造结果。

v0.5 已实现数据范围：

- 角色：Visitor、Employee、Sales、HR、Finance Manager、Admin；
- 资源：公开产品资料、客户合同、员工/工资信息、财务预算、外部供应商文档；
- 工具：单条合成客户查询；
- 场景：对象级资源越权、单条客户工具越权、固定 RAG 不可信文档 Case。

v1.0 待 F-015 实现的数据范围：

- 工具：有限合成客户导出、Mock Mail Sink；
- 场景：完整 Source→Sink 外泄和工具阈值/审批越权。

所有内容必须标注 `SYNTHETIC / DEMO ONLY`，不得放入真实个人信息、真实凭据或可用密钥。
