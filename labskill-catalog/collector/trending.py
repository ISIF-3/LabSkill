"""github.com/trending 페이지 파서.

공식 API가 없으므로 HTML 구조(article.Box-row)에 의존한다.
구조가 바뀌면 0개가 나오고, 수집기는 이를 실패로 처리한다(조용히 틀린 데이터 방지).
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

_PERIOD_RE = re.compile(r"([\d,]+)\s+stars?\s+(today|this week|this month)", re.I)
_NUM_RE = re.compile(r"[\d,]+")


def _num(text: str) -> int | None:
    m = _NUM_RE.search(text or "")
    return int(m.group().replace(",", "")) if m else None


class _TrendingParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items: list[dict] = []
        self._cur: dict | None = None
        self._in_h2 = False
        self._in_p = False
        self._in_lang = False
        self._in_star_link = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "article" and "Box-row" in (a.get("class") or ""):
            if self._cur is not None:   # 닫는 태그 없이 다음 항목이 시작되면 앞 항목을 마무리
                self._finish()
            self._cur = {"full_name": None, "description": "", "language": None,
                         "stars": None, "period_stars": None, "_text": [], "_stars_text": []}
            return
        if self._cur is None:
            return
        if tag == "h2":
            self._in_h2 = True
        elif tag == "a" and self._in_h2 and self._cur["full_name"] is None:
            href = (a.get("href") or "").strip("/")
            if href.count("/") == 1:
                self._cur["full_name"] = href
        elif tag == "p" and not self._cur["description"]:
            self._in_p = True
        elif tag == "span" and a.get("itemprop") == "programmingLanguage":
            self._in_lang = True
        elif tag == "a" and (a.get("href") or "").endswith("/stargazers"):
            self._in_star_link = True

    def handle_endtag(self, tag):
        if self._cur is None:
            return
        if tag == "article":
            self._finish()
        elif tag == "h2":
            self._in_h2 = False
        elif tag == "p":
            self._in_p = False
        elif tag == "span":
            self._in_lang = False
        elif tag == "a":
            self._in_star_link = False

    def handle_data(self, data):
        if self._cur is None:
            return
        self._cur["_text"].append(data)
        if self._in_p:
            self._cur["description"] += data
        if self._in_lang and data.strip():
            self._cur["language"] = data.strip()
        if self._in_star_link:
            self._cur["_stars_text"].append(data)

    def _finish(self):
        cur = self._cur
        self._cur = None
        self._in_h2 = self._in_p = self._in_lang = self._in_star_link = False
        if not cur or not cur["full_name"]:
            return
        text = " ".join(cur.pop("_text"))
        stars_text = " ".join(cur.pop("_stars_text"))
        cur["stars"] = _num(stars_text)
        m = _PERIOD_RE.search(text)
        if m:
            cur["period_stars"] = int(m.group(1).replace(",", ""))
            cur["period"] = m.group(2).lower()
        cur["description"] = " ".join(cur["description"].split())
        self.items.append(cur)


def parse_trending(html: str) -> list[dict]:
    """트렌딩 HTML → [{full_name, description, language, stars, period_stars, period}]"""
    p = _TrendingParser()
    p.feed(html)
    p.close()
    if p._cur is not None:
        p._finish()
    seen, out = set(), []
    for item in p.items:
        if item["full_name"] not in seen:
            seen.add(item["full_name"])
            out.append(item)
    return out
