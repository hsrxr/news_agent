# -*- coding: utf-8 -*-
"""
每日简报自动脚本 (DeepSeek-R1 推理版 + HTML 精美排版)
功能：抓取真实RSS/API数据 -> DeepSeek R1 深度思考 -> 生成 HTML 邮件发送
"""

import os
import smtplib
import ssl
import time
import feedparser
import requests
import markdown # 用于将 Markdown 转为 HTML
from email.message import EmailMessage
from datetime import datetime
from openai import OpenAI

# --- 配置区域 ---

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")

# 数据源配置 (增加了一些高质量源)
DATA_SOURCES = {
    "tech": [
        "https://36kr.com/feed",           # 36氪 (中文)
        "https://www.theverge.com/rss/index.xml", # The Verge (英文)
        "http://feeds.feedburner.com/TechCrunch/", # TechCrunch (英文)
    ],
    "finance": [
        "https://finance.yahoo.com/news/rssindex", # Yahoo Finance
        "http://feeds.marketwatch.com/marketwatch/topstories/" # MarketWatch
    ],
    "papers": [
        "http://export.arxiv.org/rss/cs.AI", # arXiv AI
        "http://export.arxiv.org/rss/cs.LG"  # arXiv Machine Learning
    ]
}

HF_DAILY_PAPERS_API = "https://huggingface.co/api/daily_papers"

# --- 核心功能函数 ---

def fetch_rss_data(urls, max_items=3):
    """抓取 RSS 数据"""
    print(f"正在抓取 RSS 数据...")
    combined_text = ""
    for url in urls:
        try:
            feed = feedparser.parse(url)
            print(f"  - 成功连接: {feed.feed.get('title', url)}")
            for entry in feed.entries[:max_items]:
                title = entry.get('title', 'No Title')
                # 去除摘要中的HTML标签，只保留文本
                summary = entry.get('summary', '')[:200].replace('<p>', '').replace('</p>', '') 
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
                summary = paper.get('summary', 'No summary')[:250].replace('\n', ' ')
                paper_id = paper.get('paper', {}).get('id', '')
                link = f"https://huggingface.co/papers/{paper_id}" if paper_id else "No Link"
                text += f"题目: {title}\n链接: {link}\n摘要: {summary}...\n\n"
            return text
        else:
            return "无法获取 HF 数据。"
    except Exception as e:
        return f"获取 Hugging Face 数据时出错: {e}"

def analyze_with_deepseek_r1(tech_text, finance_text, paper_text):
    """调用 DeepSeek-R1 (推理模型) 进行深度总结"""
    print("正在发送给 DeepSeek R1 进行深度思考 (可能需要几十秒)...")

    if not DEEPSEEK_API_KEY:
        print("❌ 错误: 未找到 DEEPSEEK_API_KEY")
        return None

    client = OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com"
    )

    # 提示词优化：要求更像 Gemini 的分析风格
    prompt = f"""
    你是一位拥有华尔街背景的资深科技分析师。请阅读以下今日的原始资讯，为我撰写一份【深度晨报】。

    【原始资讯】
    === 科技动态 ===
    {tech_text[:4000]} 
    === 金融市场 ===
    {finance_text[:4000]}
    === 学术前沿 ===
    {paper_text[:4000]}

    【撰写要求】
    1. **深度分析**：不要只是罗列新闻。我需要你分析新闻背后的趋势、对行业的影响，以及不同事件之间的联系。
    2. **结构清晰**：必须使用 Markdown 格式。
       - 使用 `##` 分割板块。
       - 使用 `**加粗**` 强调核心观点。
       - 使用 `> 引用` 标记你的独家评论。
    3. **板块安排**：
       - 📊 **市场脉搏** (Market Pulse): 重点关注大公司股价波动背后的逻辑。
       - 🤖 **AI 与科技前沿** (Tech & AI): 36氪、The Verge 等媒体的头条，以及 AI 新技术。
       - 📝 **论文精选** (Paper Watch): 用通俗易懂的语言介绍 1-2 篇最有价值的论文，并说明为什么它重要。
       - 💡 **每日洞察** (Daily Insight): 最后一段，给出你对今天整体局势的独家判断。

    4. **语气**：专业、客观、犀利。
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-reasoner",  # 【关键】切换为 R1 推理模型
            messages=[
                {"role": "user", "content": prompt},
            ],
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ DeepSeek API 调用失败: {e}")
        return None

def send_html_email(subject, markdown_content):
    """将 Markdown 转换为 HTML 并发送邮件"""
    if not EMAIL_SENDER or not EMAIL_PASSWORD or not EMAIL_RECEIVER:
        print("❌ 错误：缺少邮件配置，无法发送。")
        return

    # 1. Markdown -> HTML 转换
    html_body = markdown.markdown(markdown_content)

    # 2. 添加 CSS 样式，让邮件更好看
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }}
            h2 {{ color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px; margin-top: 30px; }}
            h3 {{ color: #34495e; margin-top: 20px; }}
            strong {{ color: #e67e22; }} /* 重点文字用橙色 */
            a {{ color: #3498db; text-decoration: none; }}
            blockquote {{ border-left: 4px solid #bdc3c7; padding-left: 15px; color: #7f8c8d; font-style: italic; background-color: #f9f9f9; padding: 10px; }}
            ul {{ padding-left: 20px; }}
            li {{ margin-bottom: 8px; }}
            .footer {{ margin-top: 40px; font-size: 12px; color: #999; text-align: center; border-top: 1px solid #eee; padding-top: 20px; }}
        </style>
    </head>
    <body>
        {html_body}
        <div class="footer">
            Generated by DeepSeek-R1 Agent · {datetime.now().strftime("%Y-%m-%d %H:%M")}
        </div>
    </body>
    </html>
    """

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    
    # 设置邮件内容为 HTML
    msg.set_content("您的邮箱不支持 HTML 格式，请使用支持 HTML 的客户端查看。") # 纯文本回退
    msg.add_alternative(html_content, subtype='html') # HTML 版本

    try:
        smtp_server = "smtp.qq.com" if "qq.com" in EMAIL_SENDER or "foxmail.com" in EMAIL_SENDER else "smtp.gmail.com"
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, 465, context=context) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
            print("✅ HTML 邮件发送成功！")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

# --- 主程序 ---

def main():
    print("--- 启动每日简报任务 (DeepSeek-R1 推理版) ---")
    
    tech_data = fetch_rss_data(DATA_SOURCES["tech"])
    finance_data = fetch_rss_data(DATA_SOURCES["finance"])
    hf_data = fetch_hf_daily_papers()
    arxiv_data = fetch_rss_data(DATA_SOURCES["papers"])
    
    all_paper_data = hf_data + "\n" + arxiv_data

    # 使用 R1 分析
    briefing_content = analyze_with_deepseek_r1(tech_data, finance_data, all_paper_data)
    
    if briefing_content:
        today = datetime.now().strftime("%Y-%m-%d")
        subject = f"【深度晨报】{today} 科技金融与AI前沿"
        # 发送 HTML 邮件
        send_html_email(subject, briefing_content)
        print("任务完成，邮件已发送。")
    else:
        print("分析失败，未发送邮件。")

if __name__ == "__main__":
    main()