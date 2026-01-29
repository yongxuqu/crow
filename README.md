# Daily AI Crow 🐦

一个基于 Streamlit 的个人 AI 情报站，自动聚合每日最新的 AI 资讯与 Reddit 独立开发灵感。

![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=Streamlit&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)

## ✨ 功能特性

- **🤖 每日 AI 资讯**：
  - 聚合 OpenAI, Google DeepMind, Anthropic, Hugging Face 等权威博客。
  - 包含 TechCrunch, The Verge, Wired 等科技媒体 AI 版块。
  - 自动过滤 24 小时内的最新内容，确保时效性。
  - 智能关键词过滤，剔除无关噪音。

- **💡 独立开发灵感**：
  - 监控 Reddit 热门板块：`r/indiehackers`, `r/SaaS`, `r/AppIdeas`, `r/SomebodyMakeThis` 等。
  - 发现最新的痛点需求与创意点子。

- **📅 历史回溯**：
  - 集成 Supabase 数据库，支持按日期查看历史情报。
  - 自动持久化每日抓取的数据。

## 🚀 快速开始

### 1. 本地运行

```bash
# 克隆仓库
git clone https://github.com/yongxuqu/crow.git
cd crow

# 安装依赖
pip install -r requirements.txt

# 配置环境变量 (.env)
# 复制 .env.example 为 .env 并填入 Supabase 密钥
cp .env.example .env

# 启动应用
streamlit run streamlit_app.py
```

### 2. 部署到 Streamlit Cloud

1. Fork 本仓库。
2. 在 Streamlit Cloud 新建应用，选择本仓库。
3. 在 Advanced Settings -> Secrets 中配置 Supabase 密钥：
   ```toml
   SUPABASE_URL = "your_url"
   SUPABASE_KEY = "your_key"
   ```
4. 点击 Deploy 即可。

## 🛠️ 技术栈

- **前端**：Streamlit
- **数据源**：RSS Feeds (Feedparser), Reddit API (Requests)
- **数据库**：Supabase (PostgreSQL)
- **数据处理**：Pandas, BeautifulSoup4
- **可视化**：Plotly

## 📝 License

MIT
