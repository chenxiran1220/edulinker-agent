

https://github.com/user-attachments/assets/9fc21ba4-7a0b-4cd0-88d8-9fffc72db047

# 🎓 EduLinker: 学术编辑部自动化联络 Agent

> **一句话简介**：专为学术组织（如 ROE 编辑部）设计的全流程寻址与邀约工具，将“学者检索-画像分析-个性化约稿”从小时级压缩至秒级。

---

## 🌟 项目亮点
- **精准寻址**：集成 Serper API，通过多步检索策略，针对教育学领域学者邮箱抓取准确率表现优异。
- **全流程工作台**：采用三层架构设计，实现从“名单导入”到“AI 邮件撰写”再到“一键发送”的闭环体验。
- **低门槛交互**：基于 Streamlit 构建，无需编程基础，编辑部成员即可上手使用。
- **飞书生态潜力**：预留多维表格接入接口，未来可实现与飞书协作平台的深度联动。

## 🛠️ 工作台架构
本项目采用模块化设计，分为两大核心模块：
1. **自动寻址引擎**：基于 Python + 正则表达式 + 实时搜索 API，动态抓取全球学者最新公开联络方式。
2. **智能联络终端**：提供邮件模板自动填充、在线预览修改，并支持通过 `mailto` 协议一键唤起本地邮件客户端。

## 🚀 快速开始

### 1. 访问线上版本
[点击此处访问已部署的 EduLinker 网页端](https://edulinker-agent-g2a2hjfqyrfb3rjwjymelp.streamlit.app/)

### 2. 本地运行
如果你想在本地环境运行本项目，请执行以下步骤：
```bash
# 克隆项目
git clone [https://github.com/chenxiran1220/edulinker-agent.git](https://github.com/chenxiran1220/edulinker-agent.git)

# 安装依赖
pip install -r requirements.txt

# 运行应用
streamlit run app.py
