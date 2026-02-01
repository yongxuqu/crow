import requests
import feedparser
import pandas as pd
from datetime import datetime
import concurrent.futures
from dateutil import parser
import pytz
import re
import os
import streamlit as st
try:
    import praw
except ImportError:
    praw = None
try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

from db_utils import (
    get_news_from_db, save_news_to_db, 
    get_reddit_from_db, save_reddit_to_db,
    get_github_trending_from_db, save_github_trending_to_db,
    get_xhs_from_db, save_xhs_to_db, delete_xhs_for_date
)
from bs4 import BeautifulSoup
import urllib.parse

def fetch_reddit_with_praw(subreddits_list, limit=10):
    """
    使用 PRAW (Reddit 官方 API) 获取数据，这是最可靠的方式。
    需要配置 REDDIT_CLIENT_ID 和 REDDIT_CLIENT_SECRET
    """
    if not praw:
        print("PRAW not installed.")
        return []

    print("Using PRAW for Reddit fetching...")
    posts_list = []
    try:
        reddit = praw.Reddit(
            client_id=st.secrets["REDDIT_CLIENT_ID"],
            client_secret=st.secrets["REDDIT_CLIENT_SECRET"],
            user_agent="streamlit:ai-indie-daily:v1.0 (by /u/anonymous)"
        )
        
        # 将列表组合成 "indiehackers+SaaS+..." 字符串一次性获取
        multi_sub = "+".join(subreddits_list)
        
        # 使用 read_only 模式获取 top
        for submission in reddit.subreddit(multi_sub).top(time_filter="day", limit=limit*len(subreddits_list)):
            posts_list.append({
                'source': f"r/{submission.subreddit.display_name}",
                'title': submission.title,
                'score': submission.score,
                'comments': submission.num_comments,
                'url': submission.url,
                'permalink': f"https://www.reddit.com{submission.permalink}",
                'created_utc': datetime.fromtimestamp(submission.created_utc).strftime('%Y-%m-%d %H:%M')
            })
            
    except Exception as e:
        print(f"PRAW Error: {e}")
        return []
        
    return posts_list

def fetch_reddit_post_metrics(link, headers):
    post_id_match = re.search(r'/comments/([a-z0-9]+)/', link)
    if not post_id_match:
        return None, None
    post_id = post_id_match.group(1)
    json_url = f"https://www.reddit.com/comments/{post_id}.json?raw_json=1"
    try:
        response = requests.get(json_url, headers=headers, timeout=5)
        if response.status_code != 200:
            return None, None
        data = response.json()
        post_data = data[0]['data']['children'][0]['data']
        return post_data.get('score'), post_data.get('num_comments')
    except Exception:
        return None, None
def fetch_reddit_subreddit(sub, limit=10):
    """
    单个 Subreddit 获取函数，用于并发执行
    优先尝试 JSON API，如果失败则回退到 RSS
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0'
    }
    posts_list = []
    print(f"Fetching r/{sub}...")
    
    # --- 尝试 1: JSON API ---
    try:
        # 使用 top.json?t=day 获取过去 24 小时内热度最高的内容
        url = f"https://www.reddit.com/r/{sub}/top.json?t=day&limit={limit*3}"
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            posts = data.get('data', {}).get('children', [])
            
            # 获取当前时间戳
            now_ts = datetime.now().timestamp()
            # 放宽时间过滤到 48 小时，避免时区差异导致数据为空
            # Reddit 的 t=day 其实已经做了一次过滤，这里的二次过滤是为了保险，但不能太严
            cutoff_ts = now_ts - 48 * 3600 
            
            for post in posts:
                p_data = post['data']
                created_utc = p_data.get('created_utc', 0)
                
                if created_utc < cutoff_ts:
                    continue
                    
                posts_list.append({
                    'source': f"r/{sub}",
                    'title': p_data.get('title'),
                    'score': p_data.get('score'),
                    'comments': p_data.get('num_comments'),
                    'url': p_data.get('url'),
                    'permalink': f"https://www.reddit.com{p_data.get('permalink')}",
                    'created_utc': datetime.fromtimestamp(created_utc).strftime('%Y-%m-%d %H:%M')
                })
        else:
            print(f"JSON API failed for r/{sub}: {response.status_code}")
    except Exception as e:
        print(f"Error fetching JSON for r/{sub}: {e}")

    # --- 尝试 2: RSS Fallback (如果 JSON 没拿到数据) ---
    if not posts_list:
        print(f"Falling back to RSS for r/{sub}...")
        try:
            rss_url = f"https://www.reddit.com/r/{sub}/top/.rss?t=day&limit={limit}"
            # 使用 requests 获取内容，带上 User-Agent，避免 feedparser 默认 UA 被封
            rss_response = requests.get(rss_url, headers=headers, timeout=5)
            
            if rss_response.status_code == 200:
                feed = feedparser.parse(rss_response.content)
                
                for entry in feed.entries[:limit]:
                    # RSS 不容易直接拿到 score/comments，尝试从 summary 解析
                    # Reddit RSS summary 通常包含 HTML 表格，里边有 score/comments
                    summary = getattr(entry, 'summary', '')
                    
                    comments_count = 0
                    comments_match = re.search(r'>(\d+)\s+comments<', summary)
                    if not comments_match:
                         comments_match = re.search(r'(\d+)\s+comments', summary)
                    
                    if comments_match:
                        comments_count = int(comments_match.group(1))
                    
                    score_count = 0
                    score_match = re.search(r'(\d+)\s+points', summary)
                    if score_match:
                        score_count = int(score_match.group(1))
                    
                    # 解析时间
                    published_dt = datetime.now()
                    if hasattr(entry, 'updated_parsed'):
                        try:
                             published_dt = datetime.fromtimestamp(datetime(*entry.updated_parsed[:6]).timestamp())
                        except:
                            pass
                    
                    # 尝试再次获取 metrics 如果 RSS 里没有 (可选，但这会增加请求量，容易被封，先注释掉)
                    # if (score_count == 0) or (comments_count == 0):
                    #    fetched_score, fetched_comments = fetch_reddit_post_metrics(entry.link, headers)
                    #    ...
    
                    posts_list.append({
                        'source': f"r/{sub}",
                        'title': entry.title,
                        'score': score_count, 
                        'comments': comments_count,
                        'url': entry.link,
                        'permalink': entry.link,
                        'created_utc': published_dt.strftime('%Y-%m-%d %H:%M')
                    })
            else:
                print(f"RSS fetch failed for r/{sub}: {rss_response.status_code}")
                
        except Exception as e:
            print(f"Error fetching RSS for r/{sub}: {e}")

    return posts_list[:limit]

def get_reddit_hot(target_date=None):
    # 如果指定了日期且不是今天，尝试从数据库获取
    today_str = datetime.now().strftime('%Y-%m-%d')
    query_date = target_date.strftime('%Y-%m-%d') if target_date else today_str
    
    if query_date != today_str:
        print(f"Querying DB for Reddit data on {query_date}...")
        db_data = get_reddit_from_db(query_date)
        if db_data:
            return pd.DataFrame(db_data)
        else:
            return pd.DataFrame() # 如果是历史日期且无数据，返回空
            
    # 如果是今天，先检查数据库有没有，没有再爬取
    # (策略：为了保证实时性，今天的数据如果 DB 有，可以返回 DB 的，但用户可能想刷新。
    # 这里我们简化逻辑：每次刷新都重新爬取并覆盖/追加？
    # 更好的逻辑：如果是今天，优先爬取，然后保存到 DB (upsert 或 覆盖))
    # 为简单起见，这里保持实时爬取，然后异步存入 DB
    
    subreddits = ['indiehackers', 'SaaS', 'sideproject', 'entrepreneur', 'startups', 'AppIdeas', 'SomebodyMakeThis']
    all_posts = []
    
    # --- 优先尝试 PRAW (官方 API) ---
    # 检查 secrets 是否配置了 Reddit Key
    has_reddit_secrets = False
    try:
        if "REDDIT_CLIENT_ID" in st.secrets and "REDDIT_CLIENT_SECRET" in st.secrets:
            has_reddit_secrets = True
    except FileNotFoundError:
        pass # 本地如果没有 .streamlit/secrets.toml 会报错
    except Exception:
        pass

    if has_reddit_secrets:
        praw_posts = fetch_reddit_with_praw(subreddits)
        if praw_posts:
            all_posts = praw_posts
    
    # 如果 PRAW 没配置或失败，回退到原来的并发抓取 (RSS/JSON)
    if not all_posts:
        if has_reddit_secrets:
            print("PRAW fetch returned empty, falling back to legacy fetcher...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_sub = {executor.submit(fetch_reddit_subreddit, sub): sub for sub in subreddits}
            for future in concurrent.futures.as_completed(future_to_sub):
                try:
                    posts = future.result()
                    all_posts.extend(posts)
                except Exception as exc:
                    print(f"Subreddit generated an exception: {exc}")
    
    if not all_posts:
        # 如果获取失败，返回 Mock 数据用于演示
        print("Warning: No data fetched from Reddit. Using mock data.")
        mock_data = [
            {
                'source': 'r/indiehackers',
                'title': '[Demo] 我如何在一周内构建了这个 SaaS 并获得了首批用户 (演示数据)',
                'score': 156,
                'comments': 42,
                'url': 'https://www.reddit.com/r/indiehackers/top/',
                'permalink': 'https://www.reddit.com/r/indiehackers/',
                'created_utc': datetime.now().strftime('%Y-%m-%d %H:%M')
            },
            {
                'source': 'r/SaaS',
                'title': '寻找独立开发者合伙人 - AI 视频生成方向 (演示数据)',
                'score': 89,
                'comments': 23,
                'url': 'https://www.reddit.com/r/SaaS/top/',
                'permalink': 'https://www.reddit.com/r/SaaS/',
                'created_utc': datetime.now().strftime('%Y-%m-%d %H:%M')
            }
        ]
        df = pd.DataFrame(mock_data)
        return df

    df = pd.DataFrame(all_posts)
    if 'score' in df.columns:
        df['score_numeric'] = pd.to_numeric(df['score'], errors='coerce')
        df = df.sort_values(by='score_numeric', ascending=False, na_position='last')
        df = df.drop(columns=['score_numeric'])
    elif 'created_utc' in df.columns:
        df = df.sort_values(by='created_utc', ascending=False)
    
    # 保存到数据库 (只保存今天的)
    save_reddit_to_db(all_posts, today_str)
    
    return df

from bs4 import BeautifulSoup

def fetch_rss_feed(feed):
    # 单个 RSS 源获取函数，用于并发执行
    news_items = []
    keywords = [
        'ai', 'gpt', 'llm', 'machine learning', 'neural', 'diffusion', 
        'artificial intelligence', 'openai', 'anthropic', 'deepmind', 
        'transformer', 'chatbot', 'copilot', 'gemini', 'claude', 'llama',
        'rag', 'agent', 'generative', 'mistral', 'hugging face',
        'cursor', 'trae', 'windsurf', 'bolt.new', 'lovable', 'vibe coding',
        'cline', 'roocline', 'aider', 'devin', 'supermaven'
    ]
    
    # 负面关键词：过滤掉报错、崩溃、求助等非资讯类内容
    negative_keywords = [
        'crash', 'error', 'bug', 'not working', 'fail', 'help', 'issue', 
        'spinning wheel', 'frozen', 'stuck', 'glitch', 'broken'
    ]
    
    print(f"Fetching {feed['name']}...")
    try:
        # 更新 User-Agent 为较新的版本，避免被 Reddit 等站点拦截
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0'}
        response = requests.get(feed['url'], headers=headers, timeout=5)
        if response.status_code != 200:
            print(f"Failed to fetch {feed['name']}: {response.status_code}")
            return []
        
        parsed = feedparser.parse(response.content)
        if not parsed.entries:
            return []
            
        # 获取当前时间（UTC）用于后续判断
        now_utc = datetime.now(pytz.utc)
    
        for entry in parsed.entries[:10]: # 每个源取前10条
            title = entry.title
            link = entry.link
            
            # 0. 通用负面关键词过滤 (针对 Reddit/HN 等社区源)
            # TechCrunch 等官方媒体通常不会有这类标题，为了保险起见全量过滤
            title_lower = title.lower()
            if any(nk in title_lower for nk in negative_keywords):
                continue

            # 0.5 过滤标题中显式标注旧年份的内容 (例如 "The 500-mile email (2002)")
            # 如果标题包含 (YYYY) 且年份早于去年，则过滤
            year_match = re.search(r'\((\d{4})\)', title)
            if year_match:
                year = int(year_match.group(1))
                current_year = datetime.now().year
                if year < current_year - 1:
                    continue
            
            # 1. 针对 Hacker News 等综合源进行关键词过滤
            if feed['name'] == 'Hacker News':
                matched = False
                for k in keywords:
                    # 使用正则 \b 匹配单词边界，避免 'ai' 匹配到 'Maine' 或 'email'
                    # 对于 'ai', 'gpt' 等短词，强制前后边界 \bkeyword\b
                    # 对于 'transformer' 等可能复数的词，只强制前边界 \bkeyword
                    if k in ['ai', 'gpt', 'llm', 'rag']:
                         pattern = r'(?i)\b' + re.escape(k) + r'\b'
                    else:
                         pattern = r'(?i)\b' + re.escape(k)
                         
                    if re.search(pattern, title):
                        matched = True
                        break
                
                if not matched:
                    continue
            
            # 解析时间
            published_str = getattr(entry, 'published', getattr(entry, 'updated', str(datetime.now())))
            try:
                published_dt = parser.parse(published_str)
                if published_dt.tzinfo is not None:
                    published_dt = published_dt.astimezone(pytz.utc)
                else:
                    published_dt = published_dt.replace(tzinfo=pytz.utc)
            except:
                published_dt = datetime.now(pytz.utc)
            
            # 动态调整时间窗口
            # 用户反馈希望严格看到“最新”日期，因此统一设置为 48 小时
            # 这样可以容纳时区差异，但不会显示一周前的内容
            # 如果是 Hacker News/Reddit 这种高频源，依然保持 24 小时
            is_high_freq = any(n in feed['name'] for n in ['Hacker News', 'Reddit'])
            time_window_hours = 24 if is_high_freq else 48
            
            if (now_utc - published_dt).total_seconds() > time_window_hours * 3600:
                continue

            # 处理摘要：去除 HTML 标签
            raw_summary = getattr(entry, 'summary', getattr(entry, 'description', ''))
            soup = BeautifulSoup(raw_summary, 'html.parser')
            clean_summary = soup.get_text(separator=' ').strip()
            
            # 针对 Hacker News 的特殊处理
            if feed['name'] == 'Hacker News':
                # Hacker News 的摘要通常只是 "Comments"，没有什么信息量，直接置空或者给个提示
                if 'Comments' in clean_summary or len(clean_summary) < 5:
                    clean_summary = "点击下方链接阅读 Hacker News 上的原文与讨论"

            news_items.append({
                'source': feed['name'],
                'title': title,
                'link': link,
                'published': published_dt, # 存储 datetime 对象用于排序
                'published_str': published_dt.strftime('%Y-%m-%d %H:%M'), # 用于展示
                'summary': clean_summary[:200] + '...' if len(clean_summary) > 200 else clean_summary
            })
    except Exception as e:
        print(f"Error fetching {feed['name']}: {e}")
    return news_items

def get_ai_news(target_date=None):
    # 如果指定了日期且不是今天，尝试从数据库获取
    today_str = datetime.now().strftime('%Y-%m-%d')
    query_date = target_date.strftime('%Y-%m-%d') if target_date else today_str
    
    if query_date != today_str:
        print(f"Querying DB for AI News on {query_date}...")
        db_data = get_news_from_db(query_date)
        if db_data:
            return pd.DataFrame(db_data)
        else:
            return pd.DataFrame()
            
    rss_feeds = [
        {'name': 'TechCrunch AI', 'url': 'https://techcrunch.com/category/artificial-intelligence/feed/'},
        {'name': 'The Verge AI', 'url': 'https://www.theverge.com/rss/artificial-intelligence/index.xml'},
        {'name': 'Wired AI', 'url': 'https://www.wired.com/feed/category/artificial-intelligence/latest/rss'},
        {'name': 'MIT Tech Review', 'url': 'https://www.technologyreview.com/topic/artificial-intelligence/feed'},
        {'name': 'VentureBeat AI', 'url': 'https://venturebeat.com/category/ai/feed/'},
        {'name': 'OpenAI Blog', 'url': 'https://openai.com/blog/rss.xml'},
        {'name': 'Google Research', 'url': 'https://research.google/blog/rss'},
        {'name': 'Google DeepMind', 'url': 'https://deepmind.google/blog/rss.xml'},
        {'name': 'Hugging Face', 'url': 'https://huggingface.co/blog/feed.xml'},
        {'name': 'NVIDIA Blog', 'url': 'https://blogs.nvidia.com/blog/category/deep-learning/feed/'},
        {'name': 'BAIR Blog', 'url': 'https://bair.berkeley.edu/blog/feed.xml'},
        {'name': 'Reddit LocalLLaMA', 'url': 'https://www.reddit.com/r/LocalLLaMA/top/.rss?t=day'},
        {'name': 'Reddit Cursor', 'url': 'https://www.reddit.com/r/cursor/top/.rss?t=day'},
        {'name': 'Hacker News', 'url': 'https://news.ycombinator.com/rss'}
    ]
    
    all_news = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_feed = {executor.submit(fetch_rss_feed, feed): feed for feed in rss_feeds}
        for future in concurrent.futures.as_completed(future_to_feed):
            try:
                items = future.result()
                all_news.extend(items)
            except Exception as exc:
                print(f"RSS feed generated an exception: {exc}")
    
    if not all_news:
        print("Warning: No AI news fetched. Using mock data.")
        mock_news = [
            {'source': 'OpenAI Blog', 'title': 'GPT-5 发布预告：更强的推理能力', 'link': 'https://openai.com', 'published': datetime.now(pytz.utc), 'published_str': datetime.now().strftime('%Y-%m-%d %H:%M'), 'summary': 'OpenAI 今天宣布了下一代模型的预览...'},
            {'source': 'Hacker News', 'title': 'Show HN: 一个开源的本地 LLM 运行器', 'link': 'https://news.ycombinator.com', 'published': datetime.now(pytz.utc), 'published_str': datetime.now().strftime('%Y-%m-%d %H:%M'), 'summary': '支持 Llama 3, Mistral 等模型...'}
        ]
        return pd.DataFrame(mock_news)
    
    # 按时间倒序排序
    df = pd.DataFrame(all_news)
    df = df.sort_values(by='published', ascending=False)
    
    # 保存到数据库 (只保存今天的)
    # 注意：为了避免 datetime 对象序列化问题，save_news_to_db 内部会处理
    save_news_to_db(all_news, today_str)
    
    return df

def fetch_github_trending_raw():
    """
    抓取 GitHub Trending 页面
    """
    url = "https://github.com/trending"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    print("Fetching GitHub Trending...")
    items = []
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"Failed to fetch GitHub Trending: {response.status_code}")
            return []
            
        soup = BeautifulSoup(response.content, 'html.parser')
        rows = soup.select('.Box-row')
        
        for row in rows:
            try:
                # Repo Name and Link
                h2_a = row.select_one('h2 a')
                if not h2_a: continue
                
                repo_name = h2_a.text.strip().replace('\n', '').replace(' ', '')
                repo_url = f"https://github.com{h2_a['href']}"
                
                # Description
                p_desc = row.select_one('p')
                description = p_desc.text.strip() if p_desc else ""
                
                # Language
                lang_span = row.select_one('span[itemprop="programmingLanguage"]')
                language = lang_span.text.strip() if lang_span else "Unknown"
                
                # Stars
                # Usually there are two links with svg icons for stars and forks.
                # Total stars is the first one.
                # Today stars is just text in a span usually at the end.
                
                footer_links = row.select('div.f6 a')
                total_stars = 0
                if footer_links:
                    total_stars_str = footer_links[0].text.strip().replace(',', '')
                    try:
                        total_stars = int(total_stars_str)
                    except:
                        pass
                        
                stars_today_span = row.select_one('span.d-inline-block.float-sm-right')
                stars_today = 0
                if stars_today_span:
                    stars_today_text = stars_today_span.text.strip()
                    # extract number from "123 stars today"
                    match = re.search(r'(\d+)', stars_today_text.replace(',', ''))
                    if match:
                        stars_today = int(match.group(1))
                
                items.append({
                    'repo_name': repo_name,
                    'description': description,
                    'language': language,
                    'stars_today': stars_today,
                    'total_stars': total_stars,
                    'url': repo_url
                })
                
            except Exception as e:
                print(f"Error parsing a GitHub row: {e}")
                continue
                
    except Exception as e:
        print(f"Error fetching GitHub Trending: {e}")
        
    return items

def get_github_trending(target_date=None):
    # 如果指定了日期且不是今天，尝试从数据库获取
    today_str = datetime.now().strftime('%Y-%m-%d')
    query_date = target_date.strftime('%Y-%m-%d') if target_date else today_str
    
    if query_date != today_str:
        print(f"Querying DB for GitHub Trending on {query_date}...")
        db_data = get_github_trending_from_db(query_date)
        if db_data:
            return pd.DataFrame(db_data)
        else:
            return pd.DataFrame()
            
    # 如果是今天，直接爬取
    items = fetch_github_trending_raw()
    
    if not items:
        # Mock data if failed
        print("Using mock GitHub data")
        items = [
            {
                'repo_name': 'mock/repo-1',
                'description': '这是一个演示项目 (Fetch Failed)',
                'language': 'Python',
                'stars_today': 120,
                'total_stars': 5000,
                'url': 'https://github.com'
            },
            {
                'repo_name': 'mock/repo-2',
                'description': '另一个演示项目',
                'language': 'TypeScript',
                'stars_today': 85,
                'total_stars': 2300,
                'url': 'https://github.com'
            }
        ]
        
    # 存入数据库
    if items and items[0]['repo_name'] != 'mock/repo-1':
        save_github_trending_to_db(items, today_str)
        
    return pd.DataFrame(items)

import json

def fetch_xhs_search_serper(keywords):
    """
    使用 Serper.dev API (Google Search Wrapper) 搜索小红书
    这是最稳定、最适合云端部署的方案，不会被反爬拦截。
    需要配置 SERPER_API_KEY
    """
    api_key = None
    try:
        if "SERPER_API_KEY" in st.secrets:
            api_key = st.secrets["SERPER_API_KEY"]
    except:
        pass
        
    if not api_key:
        return []
        
    print(f"Using Serper API for XHS: {keywords}")
    url = "https://google.serper.dev/search"
    
    # 构造 Payload
    # q: 查询词
    # tbs: "qdr:w" (过去一周), "qdr:d" (过去一天)
    # num: 结果数量
    payload = json.dumps({
        "q": f"site:xiaohongshu.com {keywords}",
        "tbs": "qdr:w", 
        "num": 10
    })
    
    headers = {
        'X-API-KEY': api_key,
        'Content-Type': 'application/json'
    }
    
    items = []
    try:
        response = requests.request("POST", url, headers=headers, data=payload, timeout=10)
        if response.status_code != 200:
            print(f"Serper API failed: {response.status_code} - {response.text}")
            return []
            
        data = response.json()
        organic_results = data.get("organic", [])
        
        for res in organic_results:
            title = res.get("title")
            link = res.get("link")
            snippet = res.get("snippet", "")
            date_str = res.get("date", "") # Serper 有时会直接返回日期字段
            
            if not title or not link:
                continue
                
            # 处理日期
            if not date_str:
                date_str = datetime.now().strftime('%Y-%m-%d')
                # 尝试从 snippet 提取 "3 days ago"
                if 'days ago' in snippet:
                     try:
                        days = int(re.search(r'(\d+) days ago', snippet).group(1))
                        date_str = (datetime.now() - pd.Timedelta(days=days)).strftime('%Y-%m-%d')
                     except:
                        pass
                elif 'hours ago' in snippet:
                     date_str = datetime.now().strftime('%Y-%m-%d')
            else:
                # Serper 返回的 date 可能是 "Jan 25, 2024" 或 "2 days ago"
                if 'ago' in date_str:
                     date_str = datetime.now().strftime('%Y-%m-%d') # 简化处理
                else:
                    try:
                        parsed = parser.parse(date_str)
                        date_str = parsed.strftime('%Y-%m-%d')
                    except:
                        date_str = datetime.now().strftime('%Y-%m-%d')

            items.append({
                'title': title,
                'link': link,
                'snippet': snippet,
                'keyword': keywords,
                'date': date_str
            })
            
    except Exception as e:
        print(f"Error calling Serper API: {e}")
        
    return items

def fetch_xhs_search_ddg(keywords):
    """
    通过 DuckDuckGo Search 搜索小红书相关内容
    替代不稳定的 Bing Search
    site:xiaohongshu.com {keywords}
    """
    if not DDGS:
        print("DuckDuckGo Search not installed.")
        return []

    items = []
    query = f'site:xiaohongshu.com {keywords}'
    print(f"Searching DDG for XHS: {query}")
    
    try:
        with DDGS() as ddgs:
            # region='cn-zh' 尝试针对中国区优化，或者不加
            # time='w' (past week), 'd' (past day), 'm' (past month)
            results = ddgs.text(query, region='wt-wt', safesearch='off', time='w', max_results=10)
            
            for res in results:
                try:
                    title = res.get('title', '')
                    link = res.get('href', '')
                    snippet = res.get('body', '')
                    
                    if not title or not link:
                        continue

                    # 简单的日期提取逻辑 (DDG 返回的 body 通常没有明确日期，只能从文本里猜)
                    date_str = datetime.now().strftime('%Y-%m-%d')
                    
                    # 尝试从 snippet 提取 "2 days ago", "Jan 20" 等
                    # 这里沿用之前的逻辑，或者简化
                    if '天前' in snippet:
                         match = re.search(r'(\d+)天前', snippet)
                         if match:
                            days = int(match.group(1))
                            date_str = (datetime.now() - pd.Timedelta(days=days)).strftime('%Y-%m-%d')
                    
                    items.append({
                        'title': title,
                        'link': link,
                        'snippet': snippet,
                        'keyword': keywords,
                        'date': date_str
                    })
                except Exception as e:
                    print(f"Error parsing DDG result: {e}")
                    continue
                    
    except Exception as e:
        print(f"Error searching DDG: {e}")
        
    return items

def get_xhs_trends(target_date=None):
    # 1. 检查数据库
    today_str = datetime.now().strftime('%Y-%m-%d')
    query_date = target_date.strftime('%Y-%m-%d') if target_date else today_str
    
    if query_date != today_str:
        print(f"Querying DB for XHS on {query_date}...")
        db_data = get_xhs_from_db(query_date)
        if db_data:
            # 检查是否是已知的脏数据 (Mock Data)
            # 特征：标题包含 "求一个能自动给美妆产品试色的APP"
            is_dirty = False
            for row in db_data:
                if "求一个能自动给美妆产品试色的APP" in row.get('title', ''):
                    is_dirty = True
                    break
            
            if is_dirty:
                 print(f"Found dirty mock data in DB for {query_date}. Ignoring it.")
                 return pd.DataFrame() # 返回空，让它不要显示假数据
                 
            return pd.DataFrame(db_data)
        else:
            return pd.DataFrame() # 历史无数据
            
    # 2. 如果是今天，先检查数据库，如果有数据且不是脏数据，则返回
    # 如果是脏数据，则删除并重新抓取
    print(f"Checking DB for XHS on {today_str}...")
    db_data = get_xhs_from_db(today_str)
    if db_data:
        is_dirty = False
        for row in db_data:
            if "求一个能自动给美妆产品试色的APP" in row.get('title', ''):
                is_dirty = True
                break
        
        if is_dirty:
            print("Found dirty mock data in DB for TODAY. Deleting and re-fetching...")
            delete_xhs_for_date(today_str)
            # 继续往下执行抓取逻辑
        else:
            print("Found valid data in DB for TODAY.")
            return pd.DataFrame(db_data)
    search_queries = [
        '"美妆" "痛点" "吐槽"',
        '"拍照" "技巧" "热门"',
        '"女生" "独居" "神器"',
        '"有没有app" "美妆"',
        '"求app" "穿搭"',
        '"想做一个" "生活" -app',
        '"好用" "推荐" "冷门"'
    ]
    
    all_items = []
    
    # 串行执行
    for q in search_queries:
        # 1. 优先尝试 Serper (Google API)，最稳定
        items = fetch_xhs_search_serper(q)
        
        # 2. 如果没配置 Serper 或用完了，回退到 DuckDuckGo
        if not items:
            items = fetch_xhs_search_ddg(q)
            
        if items:
            all_items.extend(items)
            
    # 去重
    seen_links = set()
    unique_items = []
    for item in all_items:
        if item['link'] not in seen_links:
            seen_links.add(item['link'])
            unique_items.append(item)
            
    if not unique_items:
        print("No XHS data found (DDG search failed). Returning empty.")
        # 彻底移除 Mock Data，宁缺毋滥
        return pd.DataFrame()
    
    # 存入数据库
    save_xhs_to_db(unique_items, today_str)
        
    return pd.DataFrame(unique_items)

if __name__ == "__main__":
    # Test
    print("Testing Reddit Fetcher...")
    print(get_reddit_hot().head())
    print("\nTesting AI News Fetcher...")
    print(get_ai_news().head())
