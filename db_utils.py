import os
from supabase import create_client, Client
from dotenv import load_dotenv
import pandas as pd
from datetime import datetime

# 加载 .env 文件
load_dotenv()

# 初始化 Supabase 客户端
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

supabase: Client = None

if url and key:
    try:
        supabase = create_client(url, key)
    except Exception as e:
        print(f"Failed to initialize Supabase client: {e}")
else:
    print("Warning: SUPABASE_URL or SUPABASE_KEY not found in environment variables.")

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
