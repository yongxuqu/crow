import os
import streamlit as st
try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = None
from dotenv import load_dotenv
import pandas as pd
from datetime import datetime

# 加载 .env 文件
load_dotenv()

# 初始化 Supabase 客户端
# 优先尝试从 Streamlit Secrets 读取，方便云端部署
url = None
key = None

try:
    if "SUPABASE_URL" in st.secrets:
        url = st.secrets["SUPABASE_URL"]
    if "SUPABASE_KEY" in st.secrets:
        key = st.secrets["SUPABASE_KEY"]
except FileNotFoundError:
    # 本地运行时可能没有 secrets.toml，忽略错误
    pass
except Exception:
    pass

# 如果 Secrets 里没有，再尝试从环境变量读取
if not url:
    url = os.environ.get("SUPABASE_URL")
if not key:
    key = os.environ.get("SUPABASE_KEY")

supabase = None

if create_client and url and key:
    try:
        supabase = create_client(url, key)
    except Exception as e:
        print(f"Failed to initialize Supabase client: {e}")
else:
    if not create_client:
        print("Warning: 'supabase' library not found.")
    else:
        print("Warning: SUPABASE_URL or SUPABASE_KEY not found in environment variables or secrets.")

def get_news_from_db(date_str):
    """
    从 Supabase 获取指定日期的 AI 新闻
    """
    if not supabase:
        return []
    
    try:
        response = supabase.table('ai_news').select("*").eq('fetched_date', date_str).order('published', desc=True).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching news from DB: {e}")
        return []

def save_news_to_db(news_items, date_str):
    """
    保存 AI 新闻到 Supabase
    """
    if not supabase or not news_items:
        return
    
    try:
        # 准备数据，确保格式正确
        data_to_insert = []
        for item in news_items:
            data_to_insert.append({
                'source': item['source'],
                'title': item['title'],
                'link': item['link'],
                'summary': item['summary'],
                'published': item['published'].isoformat() if hasattr(item['published'], 'isoformat') else item['published'],
                'published_str': item['published_str'],
                'fetched_date': date_str
            })
            
        # 批量插入
        supabase.table('ai_news').insert(data_to_insert).execute()
        print(f"Saved {len(data_to_insert)} news items to DB for {date_str}")
    except Exception as e:
        print(f"Error saving news to DB: {e}")

def get_reddit_from_db(date_str):
    """
    从 Supabase 获取指定日期的 Reddit 热门
    """
    if not supabase:
        return []
    
    try:
        response = supabase.table('reddit_demands').select("*").eq('fetched_date', date_str).order('score', desc=True).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching reddit data from DB: {e}")
        return []

def save_reddit_to_db(reddit_items, date_str):
    """
    保存 Reddit 热门数据到 Supabase
    """
    if not supabase or not reddit_items:
        return
    
    try:
        # 准备数据
        data_to_insert = []
        for item in reddit_items:
            data_to_insert.append({
                'source': item['source'],
                'title': item['title'],
                'score': item['score'],
                'comments': item['comments'],
                'url': item['url'],
                'permalink': item['permalink'],
                'created_utc': item['created_utc'],
                'fetched_date': date_str
            })
            
        # 批量插入
        supabase.table('reddit_demands').insert(data_to_insert).execute()
        print(f"Saved {len(data_to_insert)} reddit items to DB for {date_str}")
    except Exception as e:
        print(f"Error saving reddit data to DB: {e}")

def get_github_trending_from_db(date_str):
    """
    从 Supabase 获取指定日期的 GitHub 热榜
    """
    if not supabase:
        return []
    
    try:
        response = supabase.table('github_trending').select("*").eq('fetched_date', date_str).order('stars_today', desc=True).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching github trending from DB: {e}")
        return []

def save_github_trending_to_db(items, date_str):
    """
    保存 GitHub 热榜数据到 Supabase
    """
    if not supabase or not items:
        return
    
    try:
        # 准备数据
        data_to_insert = []
        for item in items:
            data_to_insert.append({
                'repo_name': item['repo_name'],
                'description': item['description'],
                'language': item['language'],
                'stars_today': item['stars_today'],
                'total_stars': item['total_stars'],
                'url': item['url'],
                'fetched_date': date_str
            })
            
        # 批量插入
        supabase.table('github_trending').insert(data_to_insert).execute()
        print(f"Saved {len(data_to_insert)} github items to DB for {date_str}")
    except Exception as e:
        print(f"Error saving github data to DB: {e}")

def delete_xhs_for_date(date_str):
    """
    删除指定日期的小红书数据 (用于清理脏数据)
    """
    if not supabase:
        return
        
    try:
        supabase.table('xiaohongshu_trends').delete().eq('fetched_date', date_str).execute()
        print(f"Deleted XHS data for {date_str}")
    except Exception as e:
        print(f"Error deleting XHS data: {e}")

def get_xhs_from_db(date_str):
    """
    从 Supabase 获取指定日期的小红书热点
    """
    if not supabase:
        return []
    
    try:
        response = supabase.table('xiaohongshu_trends').select("*").eq('fetched_date', date_str).order('id', desc=True).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching xhs from DB: {e}")
        return []

def save_xhs_to_db(items, date_str):
    """
    保存小红书热点数据到 Supabase
    """
    if not supabase or not items:
        return
    
    try:
        # 准备数据
        data_to_insert = []
        for item in items:
            data_to_insert.append({
                'title': item['title'],
                'link': item['link'],
                'snippet': item['snippet'],
                'keyword': item.get('keyword', ''),
                'fetched_date': date_str
            })
            
        # 批量插入
        supabase.table('xiaohongshu_trends').insert(data_to_insert).execute()
        print(f"Saved {len(data_to_insert)} xhs items to DB for {date_str}")
    except Exception as e:
        print(f"Error saving xhs data to DB: {e}")
