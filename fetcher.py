# -*- coding: utf-8 -*-
"""
================================================================
  「ymx」本地抓取助手  (fetcher)
================================================================
  作用：给「ymx」网页补上"联网抓取"能力。

  为什么需要它？
    网页（浏览器）受跨域限制，抓不了亚马逊/1688。
    这个小助手跑在你自己电脑上，不受跨域限制，能真去抓。
    网页会自动检测它——在线就用它自动抓，不在线就退回手动填。

  它只监听 127.0.0.1（本机），外网访问不到，安全。

  接口：
    GET /ping                          健康检查
    GET /api/amazon/search?q=关键词      搜亚马逊商品
    GET /api/amazon/product?asin=B0XXX  抓商品详情
    GET /api/links?type=patent&q=关键词  生成专利/商标/1688 检索链接

  作者：WorkBuddy AI 帮潘信豪手搓
================================================================
"""

import gzip
import json
import os
import re
import sys
import socket
import urllib.parse
import urllib.request
import urllib.error
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8771
VERSION = "1.0"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
    "Accept-Encoding": "gzip",
    "Cache-Control": "no-cache",
}


def fetch(url, timeout=25):
    """抓一个页面，自动解 gzip。返回 (状态码, 文本)。"""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            enc = (r.headers.get("Content-Encoding") or "").lower()
            if "gzip" in enc:
                try:
                    raw = gzip.decompress(raw)
                except Exception:
                    pass
            return r.status, raw.decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        return e.code, body
    except Exception as e:
        return 0, "ERROR: %s" % e


# ------------------------------------------------------------------
# 亚马逊解析
# ------------------------------------------------------------------
def is_captcha(html):
    return bool(re.search(r"Enter the characters you see below|api-services-support@amazon", html, re.I))


def parse_search(html):
    """从亚马逊搜索结果页解析出商品列表。

    注意：亚马逊给海外 IP 展示的价格常常**包含进口费（Import Fees Deposit）**，
    会明显高于美国本土价。所以这里返回的 price 只作参考，以商品页/后台为准。
    """
    out = []
    seen = set()
    marks = [m.start() for m in re.finditer(r'data-component-type="s-search-result"', html)]
    for i, s in enumerate(marks):
        nxt = marks[i + 1] if i + 1 < len(marks) else len(html)
        block = html[s:min(nxt, s + 40000)]      # 加长度上限，防止跨商品粘连
        pre = html[max(0, s - 800):s]
        m = re.search(r'data-asin="([A-Z0-9]{10})"', pre)
        if not m:
            continue
        asin = m.group(1)
        if asin in seen:
            continue
        seen.add(asin)

        t = (re.search(r'<h2[^>]*aria-label="([^"]{8,300})"', block)
             or re.search(r"<h2[^>]*>\s*<span[^>]*>([^<]{8,300})</span>", block))
        title = re.sub(r"^Sponsored Ad\s*-\s*", "", t.group(1).strip()) if t else ""

        pm = re.search(r'a-price[^>]*>\s*<span class="a-offscreen">\$([\d,]+\.\d\d)</span>', block)
        if pm:
            price = pm.group(1).replace(",", "")
        else:
            pw = re.search(r'a-price-whole">([\d,]+)', block)
            pf = re.search(r'a-price-fraction">(\d+)', block)
            price = (pw.group(1).replace(",", "") + "." + pf.group(1)) if (pw and pf) else ""

        r = re.search(r"([\d.]+) out of 5 stars", block)
        rv = (re.search(r'aria-label="([\d,]+) ratings?"', block)
              or re.search(r's-underline-text">([\d,]+)<', block))

        out.append({
            "asin": asin,
            "title": title[:160],
            "price": price,
            "rating": r.group(1) if r else "",
            "reviews": rv.group(1).replace(",", "") if rv else "",
            "sponsored": bool(re.search(r"Sponsored Ad|赞助", block[:3000])),
            "url": "https://www.amazon.com/dp/" + asin,
        })
    return out


def parse_product(html):
    """从亚马逊商品详情页解析关键字段。"""
    def first(*pats):
        for pat in pats:
            m = re.search(pat, html, re.S)
            if m:
                return m.group(1).strip()
        return ""

    title = first(r'<span id="productTitle"[^>]*>\s*([^<]{5,400})',
                  r'<meta name="title" content="([^"]{5,400})"')
    price = first(r'<span class="a-offscreen">\$([\d,]+\.\d\d)</span>',
                  r'"priceAmount":\s*([\d.]+)',
                  r'id="priceblock_ourprice"[^>]*>\s*\$([\d,]+\.\d\d)')
    rating = first(r"([\d.]+) out of 5 stars")
    reviews = first(r"([\d,]+) ratings?")
    brand = first(r'<a id="bylineInfo"[^>]*>\s*(?:Brand:\s*)?([^<]+)</a>',
                  r'"brand"\s*:\s*"([^"]{1,60})"')
    bsr = ""
    m = re.search(r"#([\d,]+)\s+in\s+([A-Za-z][A-Za-z &]{2,40})", html)
    if m:
        bsr = "#" + m.group(1) + " in " + m.group(2).strip()

    return {
        "title": title[:200],
        "price": price,
        "rating": rating,
        "reviews": reviews,
        "brand": brand,
        "bsr": bsr,
        # 透明计划标识（页面出现 Transparency 相关字样）
        "transparency": bool(re.search(r"Transparency", html)),
        # 品牌备案线索：有 A+ 内容或品牌旗舰店
        "brand_store": bool(re.search(r"brand-sn|Visit the .{1,40} Store", html)),
        "captcha": is_captcha(html),
    }


# ------------------------------------------------------------------
# 专利 / 商标 / 1688：生成官方检索链接（无 key 时的兜底）
# ------------------------------------------------------------------
def make_links(kind, q):
    q = q or ""
    eq = urllib.parse.quote(q)
    if kind == "patent":
        return {
            "title": "美国专利检索（USPTO 官方）",
            "links": [
                {"name": "USPTO 专利公共检索（推荐，权威）",
                 "url": "https://ppubs.uspto.gov/pubwebapp/static/pages/ppubsbasic.html"},
                {"name": "USPTO 开放数据平台（申请免费 API Key 后可自动化）",
                 "url": "https://data.uspto.gov/"},
                {"name": "Espacenet 全球专利（EPO）",
                 "url": "https://worldwide.espacenet.com/patent/search?q=" + eq},
                {"name": "WIPO Patentscope（PCT 国际申请）",
                 "url": "https://patentscope.wipo.int/search/en/result.jsf?query=" + eq},
            ],
            "tip": "搜商品核心词 + 类目（如 silicone cup），重点看「Design」外观专利。"
                   "有相似外观专利且权利人非中国小厂，风险就高。",
        }
    if kind == "trademark":
        return {
            "title": "美国商标检索（USPTO 官方）",
            "links": [
                {"name": "USPTO 商标检索（官方）",
                 "url": "https://tmsearch.uspto.gov/search/search-information"},
                {"name": "USPTO 商标开放数据",
                 "url": "https://developer.uspto.gov/product/trademark-status-tsdr-api"},
            ],
            "tip": "把品牌名丢进去搜。搜到「LIVE」状态的注册商标，说明这个品牌被保护，别跟卖。",
        }
    if kind == "1688":
        return {
            "title": "1688 货源检索",
            "links": [
                {"name": "1688 搜索（按关键词）",
                 "url": "https://s.1688.com/selloffer/offer_search.htm?keywords=" + eq},
                {"name": "1688 以图搜货（有商品图时最好用）",
                 "url": "https://s.1688.com/youyuan/index.htm"},
            ],
            "tip": "1688 需要登录才能看全，且反爬严格，所以这里只给检索入口——"
                   "报价请你手动看，然后填进「1688 比价」那一栏。",
        }
    return {"title": "未知类型", "links": [], "tip": ""}


# ------------------------------------------------------------------
# HTTP 服务
# ------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)

        def q1(k, d=""):
            return (qs.get(k) or [d])[0]

        if u.path == "/ping":
            self._send(200, {"ok": True, "name": "ymx抓取助手", "version": VERSION})
            return

        if u.path == "/api/amazon/search":
            kw = q1("q").strip()
            if not kw:
                self._send(400, {"ok": False, "error": "缺少 q 参数"})
                return
            url = "https://www.amazon.com/s?k=" + urllib.parse.quote(kw)
            code, html = fetch(url)
            if code != 200:
                self._send(200, {"ok": False, "error": "亚马逊返回 HTTP %s（可能被限流，稍后再试）" % code})
                return
            if is_captcha(html):
                self._send(200, {"ok": False, "error": "被亚马逊要求输入验证码了，请过几分钟再试，或换个网络。"})
                return
            items = parse_search(html)
            self._send(200, {"ok": True, "count": len(items), "items": items[:40]})
            return

        if u.path == "/api/amazon/product":
            asin = q1("asin").strip().upper()
            if not re.match(r"^[A-Z0-9]{10}$", asin):
                self._send(400, {"ok": False, "error": "ASIN 格式不对（应该是 10 位字母数字）"})
                return
            code, html = fetch("https://www.amazon.com/dp/" + asin)
            if code != 200:
                self._send(200, {"ok": False, "error": "亚马逊返回 HTTP %s" % code})
                return
            d = parse_product(html)
            if d["captcha"]:
                self._send(200, {"ok": False, "error": "被亚马逊要求输入验证码了，过几分钟再试。"})
                return
            if not d["title"]:
                self._send(200, {"ok": False, "error": "页面没解析出内容，这个 ASIN 可能已下架。"})
                return
            d["ok"] = True
            d["asin"] = asin
            d["url"] = "https://www.amazon.com/dp/" + asin
            self._send(200, d)
            return

        if u.path == "/api/links":
            kind = q1("type", "patent")
            q = q1("q")
            self._send(200, dict(make_links(kind, q), ok=True))
            return

        self._send(404, {"ok": False, "error": "not found"})


def find_port(start=PORT):
    for p in range(start, start + 20):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    return start


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    port = find_port()
    url = "http://127.0.0.1:%d" % port
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)

    print("=" * 54)
    print("   ymx抓取助手 已启动  (v%s)" % VERSION)
    print("=" * 54)
    print("   地址：%s" % url)
    print("   回到「ymx」网页，顶部会显示「抓取助手：已连接」")
    print("   关掉这个窗口即可停止。")
    print("=" * 54)

    if os.environ.get("NO_BROWSER") != "1":
        threading.Timer(1.0, lambda: webbrowser.open(url + "/ping")).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()
