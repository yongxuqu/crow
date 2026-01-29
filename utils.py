import requests
import feedparser
import pandas as pd
from datetime import datetime
import concurrent.futures
from dateutil import parser
import pytz
import re
from db_utils import get_news_from_db, save_news_to_db, get_reddit_from_db, save_reddit_to_db
from bs4 import BeautifulSoup
def fetch_reddit_subreddit(sub, limit=10):
    """
    单个 Subreddit 获取函数，用于并发执行
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    posts_list = []
    print(f"Fetching r/{sub}...")
    try:
        # 使用 top.json?t=day 获取过去 24 小时内热度最高的内容
        # limit 稍微调大一点，以防过滤后数量太少
        url = f"https://www.reddit.com/r/{sub}/top.json?t=day&limit={limit*2}"
        # 缩短超时时间为 2 秒
        response = requests.get(url, headers=headers, timeout=2)
        
        if response.status_code == 200:
            data = response.json()
            posts = data['data']['children']
            
            # 获取当前时间戳和 24 小时前的时间戳
            now_ts = datetime.now().timestamp()
            one_day_ago_ts = now_ts - 24 * 3600
            
            for post in posts:
                p_data = post['data']
                created_utc = p_data.get('created_utc')
                
                # 双重保险：过滤掉非 24 小时内的帖子
                if created_utc < one_day_ago_ts:
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
            
            # 截取需要的数量
            posts_list = posts_list[:limit]
        else:
            print(f"Failed to fetch r/{sub}: {response.status_code}")
    except Exception as e:
        print(f"Error fetching r/{sub}: {e}")
    return posts_list

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
    
    # ... 原有爬取逻辑 ...
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

    # 按分数排序
    df = pd.DataFrame(all_posts)
    df = df.sort_values(by='score', ascending=False)
    
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
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
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

if __name__ == "__main__":
    # Test
    print("Testing Reddit Fetcher...")
    print(get_reddit_hot().head())
    print("\nTesting AI News Fetcher...")
    print(get_ai_news().head())
