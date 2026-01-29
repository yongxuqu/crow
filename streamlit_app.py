import streamlit as st
import pandas as pd
from utils import get_reddit_hot, get_ai_news, get_github_trending, get_xhs_trends
from datetime import datetime, date

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
    tab1, tab2, tab3, tab4 = st.tabs(["🤖 每日 AI 动态", "🔥 独立开发热门", "📈 GitHub 热榜", "📕 小红书热点"])

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
