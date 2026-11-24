"""Render reviewed issue data into an isolated, static preview."""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
ANCHOR = re.compile(r"[a-z][a-z0-9-]*")
PUBLIC_URL = "https://lleii.github.io/economic-observer/"


def iso(value):
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError(f"应使用 YYYY-MM-DD 日期：{value}")
    return parsed


def issue_path(day):
    return f"economic-brief-{day}.html"


def fingerprint(issue):
    return sha256(json.dumps(issue, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate(issue):
    day = iso(issue["date"])
    start = iso(issue["window_start"])
    end = iso(issue["window_end"])
    day_only = issue.get("day_only", False)
    previous_day_only = issue.get("previous_day_only", False)
    if previous_day_only and not start == end == day - timedelta(days=1):
        raise ValueError("前一日新内容的材料日期必须等于期号日期减一天")
    if day_only and not start == end == day:
        raise ValueError("单日样刊只使用本期日期的材料")
    min_days, max_days = (7, 30) if issue.get("published_site") else (3, 7)
    if not day_only and not previous_day_only and not (start <= end <= day and min_days <= (end - start).days + 1 <= max_days):
        raise ValueError(f"证据窗口应为截至当期日期的 {min_days}–{max_days} 日")
    policy = issue.get("screening_policy", "legacy")
    if policy not in {"legacy", "core-research-v1", "core-research-v2"}:
        raise ValueError(f"未知筛选规则：{policy}")
    separate_push = policy == "core-research-v2"
    core_research = policy != "legacy"
    selected = issue["selected"]
    deep_reads = issue["deep_reads"]
    sources = selected + issue["support"]
    ids = {item["id"] for item in sources}
    if len(ids) != len(sources) or not all(ANCHOR.fullmatch(key) for key in ids):
        raise ValueError("来源编号须唯一且可用于页内定位")
    urls = {item["url"] for item in sources}
    if len(urls) != len(sources):
        raise ValueError("请合并指向相同原文的条目")
    minimum_selected = 1 if core_research else 5
    max_selected = 8 if issue.get("published_site") else (11 if separate_push else 8)
    if not minimum_selected <= len(selected) <= max_selected:
        raise ValueError(f"当期需要 {minimum_selected}–{max_selected} 篇经复核的文章")
    minimum_reads = 2 if separate_push else min(2, minimum_selected)
    if not minimum_reads <= len(deep_reads) <= 3 or len({item["id"] for item in deep_reads}) != len(deep_reads):
        raise ValueError(f"精读需要 {minimum_reads}–3 篇不同的精选文章")
    if not {item["id"] for item in deep_reads} <= {item["id"] for item in selected}:
        raise ValueError("精读条目须属于当期精选")
    if separate_push and not 1 <= len(push_items(issue)) <= 8:
        raise ValueError("独立推送应有 1–8 篇经复核的文章")
    if separate_push:
        paragraphs = issue["observation"].get("paragraphs", [])
        if len(paragraphs) < 2 or any(not p.strip() for p in paragraphs):
            raise ValueError("今日总括需要多个非空段落")
    if not issue["title"].strip():
        raise ValueError("缺少日报标题")
    for item in sources:
        link = urlsplit(item["url"])
        if link.scheme not in {"https", "http"} or not link.hostname or link.username:
            raise ValueError(f"原文链接无效：{item['id']}")
        published = iso(item["published"])
        if previous_day_only and published != start:
            raise ValueError(f"前一日专刊不能混入其他日期的材料：{item['id']}")
        background = item.get("background") is True and (item in issue["support"] or separate_push)
        if not (start <= published <= end or (not day_only and background and published < start)):
            raise ValueError(f"来源日期超出证据窗口：{item['id']}")
        if not all(item[key].strip() for key in ("title", "source", "type")):
            raise ValueError(f"来源元数据不全：{item['id']}")
    for item in selected:
        if core_research:
            if item.get("screening_score", 0) < 80 or not item.get("evidence_basis", "").strip():
                raise ValueError(f"精选须有通过复评的正文证据：{item['id']}")
            if not item.get("core_relevance", "").strip():
                raise ValueError(f"须写明核心研究主线与经济行为的联系：{item['id']}")
        if not 2 <= len(set(item["keywords"])) == len(item["keywords"]) <= 4:
            raise ValueError(f"每篇文章需要 2–4 个不同关键词：{item['id']}")
        if not 40 <= len(item["core"]) <= 80 or not item["reason"].strip():
            raise ValueError(f"需要 40–80 字的核心观点和入选理由：{item['id']}")
    for group in ("judgments", "questions"):
        if not 1 <= len(issue[group]) <= 3:
            raise ValueError(f"{group} 需要 1–3 项")
    for block in [issue["observation"], *issue["judgments"], *issue["questions"]]:
        prose = block.get("text", " ".join(block.get("paragraphs", [])))
        if len(set(block["refs"])) < 2 or not set(block["refs"]) <= ids or not prose.strip():
            raise ValueError("每条跨文章分析须有两项可查来源及正文")


def push_items(issue):
    deep_ids = {item["id"] for item in issue["deep_reads"]}
    return [item for item in issue["selected"] if item["id"] not in deep_ids]


def source_meta(item):
    published = escape(item["published"])
    label = ("专题回读 · " if item.get("background") else "") + item["type"]
    return (f'<p class="meta"><span class="badge">{escape(label)}</span> '
            f'{escape(item["source"])} · <time datetime="{published}">{published}</time></p>')


def original(item):
    return (f'<a href="{escape(item["url"], quote=True)}">{escape(item["title"])}</a>')


def section(key, heading, content):
    return (f'<section id="{key}" aria-labelledby="{key}-title">'
            f'<h2 class="section-head" id="{key}-title">{heading}</h2>{content}</section>')


def page(title, active, content, style, selected="today.html", *, push=False, filename=None):
    links = (
        ("home", "index.html", "首页·每日研判"),
        ("today", selected, "今日推送" if push else "今日精选"),
        ("archive", "archive.html", "历史归档"),
    )
    navigation = []
    for key, href, label in links:
        current = ' aria-current="page"' if key == active else ""
        navigation.append(f'<a href="{href}"{current}>{label}</a>')
    metadata = ""
    if filename is not None:
        metadata = (f'<link rel="canonical" href="{PUBLIC_URL}{filename}">'
                    '<meta name="application-name" content="Economic Observatory">')
    return f"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="面向经济学研究者的经济政策与产业观察。">
<title>{escape(title)}｜经济观察</title>{metadata}<style>{style}</style></head>
<body>
<header><div class="wrap masthead"><a class="brand" href="index.html">经济观察</a>
{'<p lang="en">Economic Observatory</p>' if filename is not None else ''}
<p>数字经济、数字技术与企业发展 · 国家经济战略与政策观察</p></div></header>
<div class="wrap"><nav aria-label="主导航">{''.join(navigation)}</nav>
<main>{content}</main>
<footer>综合观察与重要判断为基于所列材料的 AI 辅助研判。原文出处及材料性质随文标注。</footer></div>
</body></html>
"""


def issue_heading(issue):
    day = issue["date"]
    window = "" if issue.get("day_only") else f' · 材料窗口 {issue["window_start"]} 至 {issue["window_end"]}'
    return (f'<p class="issue-meta">经济政策研究简报 · <time datetime="{day}">{day}</time>'
            f'{window}</p>'
            f'<h1>{escape(issue["title"])}</h1>')


def render_selected(issue, heading="今日精选"):
    cards = []
    push = issue.get("screening_policy") == "core-research-v2"
    entries = push_items(issue) if push else issue["selected"]
    for number, item in enumerate(entries, 1):
        tags = "".join(f"<li>{escape(key)}</li>" for key in item["keywords"])
        label = f'<span class="push-number">{number:02d}</span> ' if push else ""
        cards.append(
            f'<article class="entry" id="pick-{item["id"]}">{source_meta(item)}<h3>{label}{original(item)}</h3>'
            f'<p><strong>核心观点</strong>　{escape(item["core"])}</p>'
            f'<p><strong>入选理由</strong>　{escape(item["reason"])}</p>'
            f'<ul class="tags" aria-label="关键词">{tags}</ul></article>'
        )
    return section("selected", heading, '<div class="stack">' + "".join(cards) + "</div>")


def render_brief(issue, style, *, snapshot=False):
    day = issue["date"]
    production = issue.get("published_site", False)
    push = issue.get("screening_policy") == "core-research-v2"
    observation = issue["observation"]
    refs_in_use = {key for block in (observation, *issue["judgments"], *issue["questions"]) for key in block["refs"]}
    items = [item for item in issue["selected"] + issue["support"] if not push or item["id"] in refs_in_use]
    selected = {item["id"]: item for item in issue["selected"]}
    numbers = {item["id"]: number for number, item in enumerate(items, 1)}

    def refs(block):
        links = "".join(f'<a href="#source-{key}">〔{numbers[key]}〕</a>' for key in block["refs"])
        return f'<p class="references">材料依据 {links}</p>'

    def notes(block):
        return "".join(
            f'<p class="term-note"><strong>{escape(term)}</strong>　{escape(definition)}</p>'
            for term, definition in block.get("terms", {}).items()
        )

    def blocks(group):
        cards = []
        for block in group:
            detail = ""
            if block.get("keywords"):
                keywords = " · ".join(map(escape, block["keywords"]))
                detail = (f'<p class="reading-keywords">关键词　{keywords}</p>'
                          f'<p class="reading-prose"><strong>一句话总结</strong>　'
                          f'{escape(block["summary"])}</p>')
            cards.append(f'<article class="entry"><h3>{escape(block["title"])}</h3>{detail}'
                         f'<p class="reading-prose">{escape(block["text"])}</p>{notes(block)}{refs(block)}</article>')
        return '<div class="stack">' + "".join(cards) + "</div>"

    content = issue_heading(issue)
    if not snapshot:
        content += f'<p class="issue-tools"><a href="{issue_path(day)}">本期独立链接</a></p>'
    if issue.get("lead_with_readings"):
        reads = []
        for read in issue["deep_reads"]:
            item = selected[read["id"]]
            keywords = " · ".join(map(escape, item["keywords"]))
            reads.append(
                f'<article class="entry">{source_meta(item)}<h3>{original(item)}</h3>'
                f'<p class="reading-keywords">关键词　{keywords}</p>'
                f'<p class="reading-prose"><strong>一句话总结</strong>　{escape(item["core"])}</p>'
                f'<p class="reading-prose">{escape(read["connection"])}</p></article>'
            )
        content += section("reads", "本期精读" if production else "首页精选",
                           '<div class="stack">' + "".join(reads) + "</div>")
    paragraphs = observation["paragraphs"] if push else [observation["text"]]
    prose = "".join(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs)
    content += section("observation", "今日总括" if push else "今日经济与政策观察",
                       f'<div class="analysis{" paragraphs" if push else ""}">{prose}{notes(observation)}{refs(observation)}</div>')
    content += section("judgments", "重要判断", blocks(issue["judgments"]))
    if not push:
        picks = []
        for read in issue["deep_reads"]:
            item = selected[read["id"]]
            extra = f'#pick-{item["id"]}' if snapshot else f'today.html#pick-{item["id"]}'
            detail = f'<p class="references"><a href="{extra}">查看关键词和入选理由</a></p>'
            picks.append(
                f'<article class="entry">{source_meta(item)}<h3>{original(item)}</h3>'
                f'<p>{escape(item["core"])}</p><p>{escape(read["connection"])}</p>'
                f'{detail}</article>'
            )
        content += section("reads", "今日精读", '<div class="stack">' + "".join(picks) + "</div>")
    content += section("questions", "值得继续关注的问题", blocks(issue["questions"]))
    if snapshot:
        content += render_selected(issue, "今日推送" if push and not production else "今日精选")
    rows = "".join(
        f'<li id="source-{item["id"]}">{original(item)}'
        f'<div class="meta">{"背景资料 · " if item.get("background") else ""}{escape(item["type"])} · {escape(item["source"])} · '
        f'{escape(item["published"])}</div></li>' for item in items
    )
    content += section("sources", "材料来源", f'<ol class="sources">{rows}</ol>')
    filename = issue_path(day) if snapshot else ""
    document = page(day, "home", content, style, selected="#selected" if snapshot else "today.html",
                    push=push and not production, filename=filename if production else None)
    if snapshot:
        marker = f'<meta name="issue-fingerprint" content="{fingerprint(issue)}">'
        document = document.replace("</head>", marker + "</head>", 1)
    return document


def write(path, content):
    temporary = path.with_suffix(".html.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def build(issue_dir, output, style):
    issues = {}
    for path in sorted(issue_dir.glob("*.json")):
        issue = json.loads(path.read_text(encoding="utf-8-sig"))
        validate(issue)
        if path.stem != issue["date"]:
            raise ValueError(f"文件名与期号不一致：{path.name}")
        issues[issue["date"]] = issue
    output.mkdir(parents=True, exist_ok=True)
    existing = {}
    for path in output.glob("economic-brief-*.html"):
        day = path.stem.removeprefix("economic-brief-")
        iso(day)
        existing[day] = path
    if not issues:
        raise ValueError("缺少可验证的日报，首页保留上次结果")
    latest = max(issues)
    if existing and max(existing) > latest:
        raise ValueError("输入缺少已发布的最新一期，首页保留上次结果")
    for day in existing.keys() & issues.keys():
        marker = f'name="issue-fingerprint" content="{fingerprint(issues[day])}"'
        if marker not in existing[day].read_text(encoding="utf-8"):
            raise ValueError(f"日期 {day} 的历史页面已存在且输入发生变化，请保留历史版本")
    for day, issue in issues.items():
        if day not in existing:
            path = output / issue_path(day)
            write(path, render_brief(issue, style, snapshot=True))
            existing[day] = path
    newest = issues[latest]
    production = newest.get("published_site", False)
    push = newest.get("screening_policy") == "core-research-v2" and not production
    label = "今日推送" if push else "今日精选"
    selected = (f'<p class="issue-meta"><time datetime="{latest}">{latest}</time> · '
                f'<a href="{issue_path(latest)}">阅读本期完整日报</a></p>'
                f'<h1>{label}</h1>' + render_selected(newest, "推送文章" if push else "精选文章"))
    write(output / "today.html", page(label, "today", selected, style, push=push,
                                     filename="today.html" if production else None))
    archive_links = "".join(
        f'<li><a href="{issue_path(day)}"><time datetime="{day}">{day}</time></a></li>'
        for day in sorted(existing, reverse=True)
    )
    archive = f'<h1>历史归档</h1><ul class="date-list">{archive_links}</ul>'
    write(output / "archive.html", page("历史归档", "archive", archive, style, push=push,
                                       filename="archive.html" if production else None))
    write(output / "index.html", render_brief(newest, style))
    print(f"Rendered latest issue {latest} and {len(existing)} archived issue(s) in {output}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--issues", type=Path, default=ROOT / "issues")
    parser.add_argument("--output", type=Path, default=ROOT)
    args = parser.parse_args()
    if args.output.resolve() == ROOT.parent:
        parser.error("请使用独立预览目录")
    build(args.issues, args.output, (ROOT / "theme.css").read_text(encoding="utf-8-sig"))
    build_reading(args.output)


def build_reading(output):
    folder = ROOT.parent / "reading-editions"
    if not folder.exists():
        return
    readings = []
    for path in sorted(folder.glob("*.json"), reverse=True):
        issue = json.loads(path.read_text(encoding="utf-8-sig"))
        day = iso(issue["date"])
        if path.stem != issue["date"] or iso(issue["material"]) != day - timedelta(days=1):
            raise ValueError("阅读期号与前一日材料日期不一致")
        if not issue["items"]:
            raise ValueError("不能发布空阅读期刊")
        for item in issue["items"]:
            if item["published"] != issue["material"] or item["section"] not in (0, 1, 2):
                raise ValueError("阅读材料日期或来源分组错误")
            if urlsplit(item["url"]).scheme not in ("http", "https"):
                raise ValueError("阅读原文链接无效")
            if "经济观察报" in item["source"]:
                raise ValueError("已排除该来源")
        readings.append(issue)
    if not readings:
        return
    template = (ROOT / "reading-template.html").read_text(encoding="utf-8")
    old_days = sorted(p.stem.removeprefix("economic-brief-") for p in output.glob("economic-brief-*.html"))
    links = [(x["date"], f'reading-{x["date"]}.html') for x in readings]
    links += [(day, issue_path(day)) for day in old_days]
    archive = "".join(f'<a style="display:inline-block;margin:8px;color:#195f48" href="{url}">{day}</a>' for day, url in sorted(links, reverse=True))
    for issue in readings:
        data = [issue] + [x for x in readings if x["date"] != issue["date"]]
        counts = [sum(x["section"] == n for x in issue["items"]) for n in range(3)]
        notice = f'候选阅读版 · 材料日期 {issue["material"]} · 报刊 {counts[0]} 篇、中央部门 {counts[1]} 篇、机构媒体 {counts[2]} 篇。未达每类10篇；访问待复核状态随文显示。'
        html = template.replace("__ISSUES__", json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")).replace("__ARCHIVE__", archive).replace("__NOTICE__", escape(notice)).replace("__DATE__", issue["date"])
        snapshot = output / f'reading-{issue["date"]}.html'
        if not snapshot.exists():
            write(snapshot, html)
        if issue == readings[0]:
            write(output / "index.html", html)
            write(output / "today.html", html)
            write(output / "archive.html", page("历史归档", "archive", '<h1>历史归档</h1>' + archive, (ROOT / "theme.css").read_text(encoding="utf-8-sig")))


if __name__ == "__main__":
    main()
