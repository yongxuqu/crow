import streamlit as st
import pandas as pd
import os
from utils import get_reddit_hot, get_ai_news, get_github_trending, get_xhs_trends
from db_utils import supabase
from ai_helper import get_doubao_client
from datetime import datetime, date

# AI 配置 (从 Secrets 获取)
try:
    DOUBAO_API_KEY = st.secrets["doubao"]["api_key"]
    DOUBAO_MODEL_ID = st.secrets["doubao"]["model_id"]
except (FileNotFoundError, KeyError):
    # 本地开发如果没有 secrets.toml，或者 secrets 中没有相关配置
    DOUBAO_API_KEY = None
    DOUBAO_MODEL_ID = None

if not DOUBAO_API_KEY:
    # 尝试从环境变量获取 (兼容性)
    DOUBAO_API_KEY = os.environ.get("DOUBAO_API_KEY")
    DOUBAO_MODEL_ID = os.environ.get("DOUBAO_MODEL_ID")

doubao_client = get_doubao_client(api_key=DOUBAO_API_KEY, model_id=DOUBAO_MODEL_ID)

# 设置页面配置
st.set_page_config(
    page_title="AI & IndieDev Daily",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 隐藏 Streamlit 默认的菜单和页脚
hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            /* 隐藏 Deploy 按钮 */
            .stDeployButton {display:none;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# 侧边栏
with st.sidebar:
    st.title("📅 日期选择")
    selected_date = st.date_input(
        "选择要查看的日期",
        value=date.today(),
        max_value=date.today()
    )
    
    st.divider()
    st.title("关于")
    st.info(
        """
        这个 Dashboard 聚合了：
        1. 每日 AI 最新动态 (RSS)
        2. Reddit 独立开发热门需求
        3. GitHub 当日热榜
        4. 小红书热点 (美妆/拍照需求)
        
        数据源：
        - OpenAI Blog, TechCrunch AI, etc.
        - r/indiehackers, r/SaaS, etc.
        - GitHub Trending
        - Bing Search (site:xiaohongshu.com)
        """
    )
    
    # 刷新按钮 (只在今天有效，或者强制刷新)
    if st.button("🔄 刷新数据"):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    # Supabase 状态指示器
    if supabase:
        st.success("✅ Supabase 数据库已连接")
    else:
        st.error("❌ Supabase 未连接 (数据无法保存)")
        st.caption("请检查 Streamlit Secrets 配置中是否包含 SUPABASE_URL 和 SUPABASE_KEY")

# 标题
st.title(f"🚀 AI & IndieDev Daily ({selected_date.strftime('%Y-%m-%d')})")

# 加载数据函数
@st.cache_data(ttl=3600)
def load_data(target_date):
    ai_news = get_ai_news(target_date)
    reddit_hot = get_reddit_hot(target_date)
    github_trending = get_github_trending(target_date)
    xhs_trends = get_xhs_trends(target_date)
    return ai_news, reddit_hot, github_trending, xhs_trends

# 加载数据
with st.spinner('正在获取最新数据...'):
    ai_data, reddit_data, github_data, xhs_data = load_data(selected_date)

# 检查是否有数据
if ai_data.empty and reddit_data.empty and github_data.empty and xhs_data.empty:
    st.warning(f"没有找到 {selected_date} 的归档数据。如果是今天，可能是网络问题；如果是历史日期，说明当时没有抓取。")
else:
    # 页面布局
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🤖 每日 AI 动态", "🔥 独立开发热门", "📈 GitHub 热榜", "📕 小红书热点", "🧠 豆包 AI 助手"])

    with tab1:
        st.header("每日 AI 最新动态")
        if not ai_data.empty:
            for index, row in ai_data.iterrows():
                # 使用 row['published_str'] 替代 row['published']
                pub_time = row.get('published_str', str(row['published']))
                with st.expander(f"**{row['title']}** - *{row['source']}*"):
                    st.write(f"**发布时间:** {pub_time}")
                    st.write(row['summary'])
                    st.markdown(f"[阅读全文]({row['link']})")
        else:
            st.info("暂无 AI 动态数据")

    with tab2:
        st.header("Reddit 独立开发热门讨论")
        if not reddit_data.empty:
            display_df = reddit_data.copy()
            display_df['score'] = display_df['score'].apply(lambda x: "-" if pd.isna(x) or x == "N/A" else x)
            display_df['comments'] = display_df['comments'].apply(lambda x: "-" if pd.isna(x) or x == "N/A" else x)
            st.dataframe(
                display_df[['title', 'score', 'comments', 'source', 'created_utc', 'url']],
                column_config={
                    "url": st.column_config.LinkColumn("链接"),
                    "title": "标题",
                    "score": "热度",
                    "comments": "评论数",
                    "source": "板块",
                    "created_utc": "发布时间"
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info("暂无 Reddit 数据")

    with tab3:
        st.header("GitHub 当日热榜")
        if not github_data.empty:
            st.dataframe(
                github_data[['repo_name', 'description', 'language', 'stars_today', 'total_stars', 'url']],
                column_config={
                    "url": st.column_config.LinkColumn("链接"),
                    "repo_name": "项目名称",
                    "description": "简介",
                    "language": "语言",
                    "stars_today": "今日 Star",
                    "total_stars": "总 Star"
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info("暂无 GitHub 数据")

    with tab4:
        st.header("小红书热点 (美妆/拍照/女生需求)")
        st.caption("数据来源: Bing Search (site:xiaohongshu.com)，聚合关键词：美妆/拍照/独居/痛点/需求 (不仅仅是App)")
        if not xhs_data.empty:
            # 确保 date 列存在
            if 'date' not in xhs_data.columns:
                 xhs_data['date'] = selected_date.strftime('%Y-%m-%d')
            
            st.dataframe(
                xhs_data[['title', 'snippet', 'date', 'link']],
                column_config={
                    "link": st.column_config.LinkColumn("链接"),
                    "title": "标题",
                    "snippet": "内容摘要",
                    "date": "日期"
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info("暂无小红书数据")
            # 如果没有配置 Serper Key，才显示提示
            if not st.secrets.get("SERPER_API_KEY") and not os.environ.get("SERPER_API_KEY"):
                st.warning("⚠️ **抓取提示**：云端环境 (Streamlit Cloud) 可能会被 DuckDuckGo 拦截导致无数据。")
                st.markdown("""
                **建议解决方案 (一劳永逸)**：
                1. 注册 [Serper.dev](https://serper.dev/) (免费，每月2500次调用，足够个人使用)。
                2. 获取 API Key。
                3. 在 Streamlit Secrets 中添加 `SERPER_API_KEY = "你的Key"`。
                4. 只有配置了 Serper Key，才能保证在云端稳定抓取搜索结果。
                """)

    with tab5:
        st.header("🧠 豆包 AI 智能分析")
        
        if not doubao_client.client:
            st.warning("⚠️ 未配置 AI API Key，无法使用 AI 功能")
            st.info("请在 Streamlit Secrets 或环境变量中配置 `DOUBAO_API_KEY` 和 `DOUBAO_MODEL_ID`。")
            st.stop()

        st.caption(f"Powered by Doubao (Model: {DOUBAO_MODEL_ID})")
        
        # Data Source Selection
        data_options = {
            "每日 AI 动态": ai_data,
            "Reddit 独立开发热门": reddit_data,
            "GitHub 热榜": github_data,
            "小红书热点": xhs_data
        }
        
        selected_option = st.selectbox("选择要分析的数据板块:", list(data_options.keys()))
        selected_data = data_options[selected_option]
        
        if selected_data.empty:
            st.warning(f"⚠️ {selected_option} 暂无数据，无法进行 AI 分析。")
        else:
            # Prepare data context
            data_context = selected_data.head(30).to_string(index=False)
            
            if "ai_chat_history" not in st.session_state:
                st.session_state["ai_chat_history"] = []
                
            # Summarize Button
            if st.button("📝 生成核心趋势总结", type="primary", key="btn_summarize"):
                with st.spinner("豆包正在阅读数据并生成总结..."):
                    summary = doubao_client.generate_summary(data_context, context_type=selected_option)
                    
                    # Add to history
                    st.session_state["ai_chat_history"].append({"role": "user", "content": f"请总结一下 {selected_option} 的数据。"})
                    st.session_state["ai_chat_history"].append({"role": "assistant", "content": summary})
            
            # Display Chat History
            for msg in st.session_state["ai_chat_history"]:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
            
            # Chat Input
            if prompt := st.chat_input("基于数据提问 (例如: '有哪些关于 LLM 的新项目?')"):
                # Add user message
                st.session_state["ai_chat_history"].append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)
                
                # Generate response
                with st.chat_message("assistant"):
                    # Context management
                    system_prompt = f"""
                    You are an intelligent data analyst assistant.
                    Current Data Context ({selected_option}):
                    {data_context}
                    
                    Answer the user's questions based on the above data.
                    If the answer is not in the data, say so.
                    Language: Chinese (Simplified).
                    """
                    
                    messages = [{"role": "system", "content": system_prompt}]
                    messages.extend([{"role": m["role"], "content": m["content"]} for m in st.session_state["ai_chat_history"][-10:]])
                    
                    full_response = ""
                    try:
                        stream = doubao_client.chat(messages)
                        full_response = st.write_stream(stream)
                    except Exception as e:
                        st.error(f"AI Error: {e}")
                        full_response = f"Error: {e}"
                    
                    st.session_state["ai_chat_history"].append({"role": "assistant", "content": full_response})

