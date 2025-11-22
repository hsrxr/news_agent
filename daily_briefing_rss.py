# -*- coding: utf-8 -*-
"""
每日简报自动脚本 (DeepSeek 版)
功能：抓取真实RSS/API数据 -> DeepSeek V3 分析 -> 发送邮件
"""

import os
import smtplib
import ssl
import time
import feedparser
import requests
from email.message import EmailMessage
from datetime import datetime
from openai import OpenAI  # 使用 OpenAI 标准库调用 DeepSeek

# --- 配置区域 ---

# 读取环境变量
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")

# 数据源配置
DATA_SOURCES = {
    "tech": [
        "http://feeds.feedburner.com/TechCrunch/",
        "https://www.theverge.com/rss/index.xml",
        "https://36kr.com/feed", # 加一个中文源
    ],
    "finance": [
        "https://finance.yahoo.com/news/rssindex",
        "http://feeds.marketwatch.com/marketwatch/topstories/"
    ],
    "papers": [
        "http://export.arxiv.org/rss/cs.AI",
        "http://export.arxiv.org/rss/cs.CL"
    ]
}

HF_DAILY_PAPERS_API = "https://huggingface.co/api/daily_papers"

# --- 功能函数 ---

def fetch_rss_data(urls, max_items=3):
    """抓取 RSS 数据"""
    print(f"正在抓取 RSS 数据...")
    combined_text = ""
    for url in urls:
        try:
            # 设置超时，防止卡死
            feed = feedparser.parse(url)
            print(f"  - 成功连接: {feed.feed.get('title', url)}")
            for entry in feed.entries[:max_items]:
                title = entry.get('title', 'No Title')
                summary = entry.get('summary', '')[:200] # 截断摘要
                link = entry.get('link', '')
                combined_text += f"- {title}\n  摘要: {summary}...\n  链接: {link}\n\n"
        except Exception as e:
            print(f"  x 抓取失败 {url}: {e}")
    return combined_text

def fetch_hf_daily_papers():
    """抓取 Hugging Face Daily Papers"""
    print("正在抓取 Hugging Face Daily Papers...")
    try:
        response = requests.get(HF_DAILY_PAPERS_API, timeout=10)
        if response.status_code == 200:
            data = response.json()
            text = "--- Hugging Face Daily Papers ---\n"
            for paper in data[:5]: 
                title = paper.get('title', 'No Title')
                summary = paper.get('summary', 'No summary')[:200].replace('\n', ' ')
                paper_id = paper.get('paper', {}).get('id', '')
                link = f"https://huggingface.co/papers/{paper_id}" if paper_id else "No Link"
                text += f"题目: {title}\n链接: {link}\n摘要: {summary}...\n\n"
            return text
        else:
            return "无法获取 HF 数据。"
    except Exception as e:
        return f"获取 Hugging Face 数据时出错: {e}"

def analyze_with_deepseek(tech_text, finance_text, paper_text):
    """调用 DeepSeek 进行总结"""
    print("正在发送给 DeepSeek 进行分析...")

    if not DEEPSEEK_API_KEY:
        print("❌ 错误: 未找到 DEEPSEEK_API_KEY")
        return None

    # 初始化 DeepSeek 客户端 (使用 OpenAI SDK)
    client = OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com"
    )

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
    
    【原始数据】
    === 科技新闻 ===
    {tech_text[:4000]} 
    
    === 金融新闻 ===
    {finance_text[:4000]}
    
    === 论文数据 ===
    {paper_text[:4000]}
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",  # DeepSeek V3 模型
            messages=[
                {"role": "system", "content": "你是一个乐于助人的专业简报助手。"},
                {"role": "user", "content": prompt},
            ],
            temperature=1.3, # 稍微增加一点创造性
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ DeepSeek API 调用失败: {e}")
        return None

def send_email(subject, content):
    """发送邮件"""
    if not EMAIL_SENDER or not EMAIL_PASSWORD or not EMAIL_RECEIVER:
        print("❌ 错误：缺少邮件配置，无法发送。")
        return

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg.set_content(content)

    try:
        smtp_server = "smtp.qq.com" if "qq.com" in EMAIL_SENDER or "foxmail.com" in EMAIL_SENDER else "smtp.gmail.com"
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, 465, context=context) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
            print("✅ 邮件发送成功！")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

# --- 主程序 ---

def main():
    print("--- 启动每日简报任务 (DeepSeek版) ---")
    
    tech_data = fetch_rss_data(DATA_SOURCES["tech"])
    finance_data = fetch_rss_data(DATA_SOURCES["finance"])
    hf_data = fetch_hf_daily_papers()
    arxiv_data = fetch_rss_data(DATA_SOURCES["papers"])
    
    all_paper_data = hf_data + "\n" + arxiv_data

    briefing_content = analyze_with_deepseek(tech_data, finance_data, all_paper_data)
    
    if briefing_content:
        today = datetime.now().strftime("%Y-%m-%d")
        subject = f"【AI日报】{today} 科技金融与论文简报"
        send_email(subject, briefing_content)
        print("任务完成，邮件已发送。")
    else:
        print("分析失败，未发送邮件。")

if __name__ == "__main__":
    main()