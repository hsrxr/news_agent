# -*- coding: utf-8 -*-
"""
每日简报自动脚本 (真实数据版)
功能：抓取真实RSS/API数据 -> Gemini分析 -> 发送邮件
"""

import os
import json
import smtplib
import ssl
import time
import requests
import feedparser  # 需要安装 feedparser
from email.message import EmailMessage
from datetime import datetime
import urllib.request
import urllib.error

# --- 配置区域 ---

# 1. API 和 邮箱配置 (从环境变量读取，安全！)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")

# Gemini API URL
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={GEMINI_API_KEY}"

# 2. 数据源配置 (真实的 RSS / API)
DATA_SOURCES = {
    "tech": [
        "http://feeds.feedburner.com/TechCrunch/",  # TechCrunch
        "https://www.theverge.com/rss/index.xml"    # The Verge
    ],
    "finance": [
        "https://finance.yahoo.com/news/rssindex",  # Yahoo Finance
        "http://feeds.marketwatch.com/marketwatch/topstories/" # MarketWatch
    ],
    "papers": [
        "http://export.arxiv.org/rss/cs.AI",  # arXiv AI 分区
        "http://export.arxiv.org/rss/cs.CL"   # arXiv 计算语言学 (NLP)
    ]
}

# HF Daily Papers API (非官方但稳定)
HF_DAILY_PAPERS_API = "https://huggingface.co/api/daily_papers"

# --- 功能函数 ---

def fetch_rss_data(urls, max_items=5):
    """抓取 RSS 数据"""
    print(f"正在抓取 RSS 数据...")
    combined_text = ""
    for url in urls:
        try:
            feed = feedparser.parse(url)
            print(f"  - 成功连接: {feed.feed.get('title', url)}")
            # 获取前 N 条
            for entry in feed.entries[:max_items]:
                title = entry.get('title', 'No Title')
                summary = entry.get('summary', '')[:200] # 截取摘要，避免太长
                link = entry.get('link', '')
                combined_text += f"- {title}\n  摘要: {summary}...\n  链接: {link}\n\n"
        except Exception as e:
            print(f"  x 抓取失败 {url}: {e}")
    return combined_text

def fetch_hf_daily_papers():
    """抓取 Hugging Face Daily Papers"""
    print("正在抓取 Hugging Face Daily Papers...")
    try:
        # 获取当天的日期 (YYYY-MM-DD)
        date_str = datetime.now().strftime("%Y-%m-%d")
        # 注意：HF API 只要请求 date 参数即可，或者直接请求 list
        response = requests.get(HF_DAILY_PAPERS_API, timeout=10)
        
        if response.status_code == 200:
            papers = response.json()
            # 取最新的 5 篇
            text = "--- Hugging Face Daily Papers ---\n"
            for paper in papers[:5]: 
                title = paper.get('title', 'No Title')
                # 这里的 summary 往往是摘要，可能很长，稍微截断
                summary = paper.get('summary', 'No summary')[:300].replace('\n', ' ')
                paper_id = paper.get('paper', {}).get('id', '')
                link = f"https://huggingface.co/papers/{paper_id}" if paper_id else "No Link"
                
                text += f"题目: {title}\n链接: {link}\n摘要: {summary}...\n\n"
            return text
        else:
            return "无法获取 Hugging Face 数据 (Status Code Error)."
    except Exception as e:
        return f"获取 Hugging Face 数据时出错: {e}"

def analyze_with_gemini(tech_text, finance_text, paper_text):
    """调用 Gemini 进行总结"""
    print("正在发送给 Gemini 进行分析...")
    
    prompt = f"""
    你是一个专业的科技与金融情报分析师。请根据以下抓取到的原始数据，为我写一份日报。
    
    【要求】
    1. 语言：中文。
    2. 格式：清晰的 Markdown 格式。
    3. 结构：
       - 🏦 金融市场 (分析市场情绪，重点新闻)
       - 🚀 科技前沿 (大厂动态，新硬件/软件)
       - 📑 论文速递 (重点介绍 Hugging Face 和 arXiv 上有价值的 AI 论文)
       - 💡 深度洞察 (基于以上信息，给出一两句你的独家分析)
    4. 风格：专业、简洁、客观。不要罗列所有新闻，挑选最重要的。
    
    【原始数据】
    
    === 科技新闻 ===
    {tech_text[:5000]} 
    
    === 金融新闻 ===
    {finance_text[:5000]}
    
    === 论文数据 ===
    {paper_text[:5000]}
    """
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    headers = {'Content-Type': 'application/json'}
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(GEMINI_API_URL, data=data, headers=headers, method='POST')
    
    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                result = json.loads(response.read().decode('utf-8'))
                return result['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        print(f"Gemini API 调用失败: {e}")
        return None

def send_email(subject, content):
    """发送邮件"""
    if not EMAIL_SENDER or not EMAIL_PASSWORD or not EMAIL_RECEIVER:
        print("错误：缺少邮件配置，无法发送。")
        return

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg.set_content(content)

    try:
        # 如果是 QQ/Foxmail，使用 SSL 465 端口
        # 如果是 Gmail，也是 465 SSL
        smtp_server = "smtp.qq.com" if "qq.com" in EMAIL_SENDER or "foxmail.com" in EMAIL_SENDER else "smtp.gmail.com"
        
        print(f"连接 SMTP 服务器: {smtp_server}...")
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, 465, context=context) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
            print("✅ 邮件发送成功！")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

# --- 主程序 ---

def main():
    print("--- 启动每日简报任务 ---")
    
    # 1. 获取真实数据
    tech_data = fetch_rss_data(DATA_SOURCES["tech"])
    finance_data = fetch_rss_data(DATA_SOURCES["finance"])
    hf_data = fetch_hf_daily_papers()
    arxiv_data = fetch_rss_data(DATA_SOURCES["papers"])
    
    all_paper_data = hf_data + "\n" + arxiv_data

    # 2. 分析
    briefing_content = analyze_with_gemini(tech_data, finance_data, all_paper_data)
    
    if briefing_content:
        # 3. 发送
        today = datetime.now().strftime("%Y-%m-%d")
        subject = f"【AI日报】{today} 科技金融与论文简报"
        send_email(subject, briefing_content)
        print(briefing_content) # 在日志里也打印一份
    else:
        print("分析失败，未发送邮件。")

if __name__ == "__main__":
    main()