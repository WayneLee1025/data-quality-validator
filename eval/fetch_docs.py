"""抓取公开监管文件正文，清洗成纯文本，供 RAG 评测使用。

只处理公开文件，不涉及任何机构内部资料。
输出到 eval/docs/，该目录已加入 .gitignore，不进公开仓库。
"""

import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

DOCS = Path(__file__).resolve().parent / "docs"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

SOURCES = [
    {
        "name": "A_数据安全管理办法.txt",
        "url": "https://www.gov.cn/zhengce/zhengceku/202412/content_6995081.htm",
        "start": "银行保险机构数据安全管理办法",
        "title": "银行保险机构数据安全管理办法（金规〔2024〕24号，2024-12-27 发布）",
    },
    {
        "name": "B_数据治理指引.txt",
        "url": "https://www.gov.cn/zhengce/zhengceku/2018-12/31/content_5450808.htm",
        "start": "银行业金融机构数据治理指引",
        "title": "银行业金融机构数据治理指引（银保监发〔2018〕22号，2018-05-21 发布）",
    },
]


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.buf = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in ("p", "div", "br", "h1", "h2", "h3", "tr", "li"):
            self.buf.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(data)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    raw = urllib.request.urlopen(req, timeout=30).read()
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def clean(html):
    p = TextExtractor()
    p.feed(html)
    txt = "".join(p.buf)
    txt = re.sub(r"[ \t\u3000]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n", txt).strip()
    return txt


def cut(txt, start_marker):
    """从正文标题处截断，去掉页面导航和页尾。

    gov.cn 政策页会同时输出 PC 版和移动版两份正文，
    表现为"第一章"出现两次，取第一份即可。
    """
    heads = [m.start() for m in re.finditer("第一章", txt)]
    if not heads:
        return ""
    end = heads[1] if len(heads) > 1 else len(txt)
    return txt[heads[0]:end].strip()


def main():
    DOCS.mkdir(parents=True, exist_ok=True)
    for s in SOURCES:
        html = fetch(s["url"])
        body = cut(clean(html), s["start"])
        out = DOCS / s["name"]
        out.write_text(f"{s['title']}\n来源：{s['url']}\n\n{body}\n", encoding="utf-8")
        print(f"{s['name']}: {len(body)} 字")


if __name__ == "__main__":
    main()
