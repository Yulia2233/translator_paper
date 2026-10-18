"""Prepare, crop, build and structurally check an offline paper translation library."""
from __future__ import annotations

import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import quote, unquote, urlsplit

ASSETS = Path(__file__).resolve().parents[1] / 'assets'
PAGE_HEADING = re.compile(r'^## 原文第\s*(\d+)\s*页\s*$', re.M)


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def metadata(pdf, document, paper_id):
    return {'schema_version': 1, 'id': paper_id, 'source_filename': pdf.name,
            'source_sha256': digest(pdf), 'pages': len(document)}


def register(pdf, folder, paper_id=None):
    import pymupdf
    with pymupdf.open(pdf) as doc:
        value = metadata(pdf, doc, paper_id or folder.name)
    path = folder / 'paper.json'
    if path.exists():
        old = json.loads(path.read_text(encoding='utf-8'))
        if old['source_sha256'] != value['source_sha256']:
            raise ValueError(f'Different source already registered: {folder}')
    folder.mkdir(parents=True, exist_ok=True)
    write_json(path, value)
    return value


def prepare(args):
    import pymupdf
    from pypdf import PdfReader
    files = []
    for value in args.input:
        path = Path(value).resolve()
        if path.is_dir():
            iterator = path.rglob('*') if args.recursive else path.iterdir()
            files.extend(p for p in iterator if p.is_file() and p.suffix.lower() == '.pdf')
        elif path.is_file() and path.suffix.lower() == '.pdf':
            files.append(path)
        else:
            raise ValueError(f'Not a PDF or directory: {path}')
    files = sorted(set(files))
    if not files:
        raise ValueError('No PDF files selected.')
    stems = [p.stem.casefold() for p in files]
    if len(stems) != len(set(stems)):
        raise ValueError('Duplicate PDF filenames: prepare separately with distinct paper directories.')
    if any(p.stem.casefold() in {'.work', 'assets'} for p in files):
        raise ValueError('A selected filename conflicts with a reserved output directory.')
    out = Path(args.out).resolve()
    records = []
    for pdf in files:
        folder = out / pdf.stem
        info = register(pdf, folder)
        work = out / '.work' / pdf.stem
        for directory in [work, folder / 'pages', folder / 'figures']:
            directory.mkdir(parents=True, exist_ok=True)
        reader = PdfReader(pdf)
        blocks, captions, extracted = [], [], []
        with pymupdf.open(pdf) as doc:
            for i, page in enumerate(doc):
                text = reader.pages[i].extract_text() or ''
                extracted.append(f'===== PAGE {i+1} =====\n\n{text}')
                (work / f'page-{i+1:03}.txt').write_text(text, encoding='utf-8')
                (work / f'page-{i+1:03}-layout.txt').write_text(
                    page.get_text('text', sort=True), encoding='utf-8')
                items = [{'bbox': list(b[:4]), 'text': b[4]}
                         for b in page.get_text('blocks', sort=True) if b[6] == 0]
                blocks.append({'page': i+1, 'width': page.rect.width,
                               'height': page.rect.height, 'rotation': page.rotation, 'blocks': items})
                for item in items:
                    if re.match(r'\s*(?:Figure|Fig\.|Table|图|表)\s*[A-Z]?\.?\d+', item['text']):
                        captions.append({'page': i+1, **item})
                page.get_pixmap(dpi=args.dpi, alpha=False).save(folder / 'pages' / f'page-{i+1:03}.png')
        raw = '\n\n'.join(extracted)
        (work / 'source.txt').write_text(raw, encoding='utf-8')
        (folder / '原文提取.txt').write_text(raw, encoding='utf-8')
        write_json(work / 'blocks.json', blocks)
        write_json(work / 'captions.json', captions)
        records.append(info)
    print(json.dumps(records, ensure_ascii=False, indent=2))


def crop(args):
    import pymupdf
    pdf, folder = Path(args.pdf).resolve(), Path(args.paper).resolve()
    meta = register(pdf, folder)
    specs = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    if not isinstance(specs, list) or not specs:
        raise ValueError('Crop manifest must be a nonempty JSON array.')
    dest = folder / 'figures'
    dest.mkdir(exist_ok=True)
    previous = dest / 'manifest.json'
    merged = {item['file']: item for item in json.loads(previous.read_text(encoding='utf-8'))} if previous.exists() else {}
    pending = []
    names = set()
    with pymupdf.open(pdf) as doc:
        # Validate every requested box before writing any requested crops.
        for item in specs:
            kind, ident = item.get('kind', 'figure'), str(item['id'])
            if kind not in {'figure', 'table', 'equation'} or not re.fullmatch(r'[A-Za-z0-9_-]+', ident):
                raise ValueError(f'Invalid crop kind/id: {item}')
            number = item['page']
            if type(number) is not int or not 1 <= number <= len(doc):
                raise ValueError(f'Invalid crop page: {item}')
            bbox = item['bbox']
            if len(bbox) != 4 or not all(isinstance(v, (int, float)) for v in bbox):
                raise ValueError(f'Invalid crop coordinates: {item}')
            box = pymupdf.Rect(bbox)
            if box.is_empty or box.is_infinite or not doc[number-1].rect.contains(box):
                raise ValueError(f'Crop outside page or empty: {item}')
            name = f'{kind}-{ident}.png'
            if name in names:
                raise ValueError(f'Duplicate crop output: {name}')
            names.add(name)
            pending.append((number, box, {'kind': kind, 'id': ident, 'file': name,
                'page': number, 'bbox': bbox, 'label': item.get('label', ''),
                'source_sha256': meta['source_sha256'], 'dpi': args.dpi}))
        for number, box, record in pending:
            doc[number-1].get_pixmap(dpi=args.dpi, clip=box, alpha=False).save(dest / record['file'])
            merged[record['file']] = record
    write_json(previous, sorted(merged.values(), key=lambda x: (x['page'], x['file'])))
    print(f'Wrote {len(pending)} crops to {dest}')


def split_translation(text, expected):
    chunks = PAGE_HEADING.split(text)
    pages = [(int(chunks[i]), chunks[i+1]) for i in range(1, len(chunks), 2)]
    if [n for n, _ in pages] != list(range(1, expected+1)):
        raise ValueError(f'Expected continuous translation pages 1–{expected}, got {[n for n, _ in pages]}')
    first = text.splitlines()[0] if text.splitlines() else ''
    if not first.startswith('# '):
        raise ValueError('Translation must start with a Markdown H1 title.')
    for number, body in pages:
        marker = None
        for line in body.splitlines():
            match = re.match(r'^\s{0,3}(`{3,}|~{3,})(.*)$', line)
            if not match:
                continue
            fence, rest = match.groups()
            if marker is None:
                marker = fence
            elif fence[0] == marker[0] and len(fence) >= len(marker) and not rest.strip():
                marker = None
        if marker:
            raise ValueError(f'Unclosed code fence on page {number}')
        if not body.strip():
            raise ValueError(f'Empty translation page {number}')
    return first[2:].strip(), chunks[0], pages


def convert(text):
    import markdown
    # Protect code before math extraction so source code containing $ or LaTeX is unchanged.
    prefix = 'PAPER' + hashlib.sha256(text.encode()).hexdigest()[:12].upper()
    codes, maths = [], []
    def code_stash(match):
        codes.append(match.group(0))
        return f'{prefix}CODE{len(codes)-1}END'
    lines = text.splitlines(keepends=True)
    pieces, i = [], 0
    while i < len(lines):
        opening = re.match(r'^ {0,3}(`{3,}|~{3,})', lines[i])
        if not opening:
            pieces.append(lines[i])
            i += 1
            continue
        marker, end = opening.group(1), i + 1
        while end < len(lines):
            closing = re.match(r'^ {0,3}(`{3,}|~{3,})\s*$', lines[end])
            if closing and closing.group(1)[0] == marker[0] and len(closing.group(1)) >= len(marker):
                break
            end += 1
        if end == len(lines):
            raise ValueError('Cannot render an unclosed code fence.')
        # Python-Markdown expects identical opening/closing fence lengths at column zero.
        # Normalize only the wrapper; the literal code contents remain unchanged.
        opening_tail = lines[i][opening.end():]
        codes.append(marker + opening_tail + ''.join(lines[i+1:end]) + marker + '\n')
        pieces.append(f'{prefix}CODE{len(codes)-1}END\n')
        i = end + 1
    protected = re.sub(r'(`+)([^\n]*?)\1', code_stash, ''.join(pieces))
    math_pattern = r'\\\[(.*?)\\\]|\$\$(.*?)\$\$|\\\((.*?)\\\)|(?<!\$)\$(?!\$)([^\n$]+?)\$(?!\$)'
    def math_stash(match):
        maths.append((next(g for g in match.groups() if g is not None),
                      match.group(1) is not None or match.group(2) is not None))
        return f'{prefix}MATH{len(maths)-1}END'
    protected = re.sub(math_pattern, math_stash, protected, flags=re.S)
    for i, code in enumerate(codes):
        protected = protected.replace(f'{prefix}CODE{i}END', code)
    md = markdown.Markdown(extensions=['tables', 'fenced_code', 'sane_lists'])
    md.preprocessors.deregister('html_block')
    md.inlinePatterns.deregister('html')
    result = md.convert(protected)
    for i, (body, display) in enumerate(maths):
        start, end = ('\\[', '\\]') if display else ('\\(', '\\)')
        tag = 'div' if display else 'span'
        replacement = f'<{tag} class="math-{ "display" if display else "inline" }">{start}{html.escape(body)}{end}</{tag}>'
        result = result.replace(f'{prefix}MATH{i}END', replacement)
    # Raw source HTML is disabled above; disallow executable Markdown link schemes as well.
    result = re.sub(r'href="\s*(?:javascript|data|vbscript):[^"]*"', 'href="#"', result, flags=re.I)
    return re.sub(r'<table>(.*?)</table>', r'<div class="tablewrap"><table>\1</table></div>', result, flags=re.S)


MATH_SCRIPTS = r'''<script src="../assets/katex.min.js"></script>
<script src="../assets/auto-render.min.js"></script>
<script>document.addEventListener('DOMContentLoaded',()=>{renderMathInElement(document.body,{
delimiters:[{left:'\\[',right:'\\]',display:true},{left:'\\(',right:'\\)',display:false}],
throwOnError:false,strict:false,trust:false});});</script>'''


def shell(title, content, asset_prefix='', math=False):
    escaped = html.escape(title)
    return (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escaped}</title>'
        f'<link rel="stylesheet" href="{asset_prefix}assets/reader.css">'
        + (f'<link rel="stylesheet" href="{asset_prefix}assets/katex.min.css">' if math else '')
        + f'</head><body>{content}' + (MATH_SCRIPTS if math else '') + '</body></html>')


def discover(out):
    paths = sorted(out.glob('*/paper.json'))
    if not paths:
        raise ValueError('No paper.json files found. Run prepare or adopt first.')
    return [(p.parent, json.loads(p.read_text(encoding='utf-8'))) for p in paths]


def build(args):
    out = Path(args.out).resolve()
    papers = discover(out)
    # Reject incomplete translations before replacing any reading pages.
    prepared = []
    for folder, info in papers:
        text = (folder / '中文逐句翻译.md').read_text(encoding='utf-8')
        prepared.append((folder, info, text, split_translation(text, info['pages'])))
    shutil.copytree(ASSETS, out / 'assets', dirs_exist_ok=True)
    records, cards = [], []
    for folder, info, text, (title, intro, pages) in prepared:
        n_pages = info['pages']
        figures = sorted((folder / 'figures').glob('figure-*.png'))
        extra = sorted((folder / 'figures').glob('table-*.png')) + sorted((folder / 'figures').glob('equation-*.png'))
        nav = '<nav aria-label="原文页码">' + ''.join(
            f'<a href="#page-{n}">第 {n} 页</a>' for n, _ in pages) + '<a href="#figures">全部图件</a></nav>'
        articles = []
        for number, body in pages:
            original = f'pages/page-{number:03}.png'
            articles.append(f'<article id="page-{number}"><div class="pagebar">'
                f'<strong>原文第 {number} 页 / 共 {n_pages} 页</strong>'
                f'<a target="_blank" rel="noopener" href="{original}">打开原页截图 ↗</a></div>{convert(body)}'
                f'<details><summary>展开本页原文截图</summary><a href="{original}" target="_blank">'
                f'<img loading="lazy" src="{original}" alt="原文第 {number} 页"></a></details></article>')
        gallery = '<section class="gallery" id="figures"><h2>原文图件</h2><p>点击打开原尺寸图片；中文对应见译文。</p><div class="figuregrid">'
        gallery += ''.join(f'<a href="figures/{quote(p.name)}" target="_blank">'
            f'<img loading="lazy" src="figures/{quote(p.name)}" alt="{html.escape(p.stem)}">{html.escape(p.stem)}</a>'
            for p in figures + extra) + '</div></section>'
        content = f'<header><a href="../index.html">← 全部论文</a><h1>{html.escape(title)}</h1>'
        content += f'<div class="sub">{html.escape(folder.name)} · {n_pages} 页 · {len(figures)} 幅图 · '
        content += '<a href="中文逐句翻译.md">Markdown 译文</a> · <a href="原文提取.txt">提取原文</a></div></header>'
        content += f'<div class="layout">{nav}<main><section class="intro">{convert(intro)}</section>'
        content += ''.join(articles) + gallery + '</main></div>'
        (folder / '中文阅读版.html').write_text(shell(title, content, '../', True), encoding='utf-8')
        record = {'id': folder.name, 'title': title, 'pages': n_pages, 'figures': len(figures),
                  'extra_crops': len(extra), 'translation_characters': len(text),
                  'html': f'{folder.name}/中文阅读版.html', 'markdown': f'{folder.name}/中文逐句翻译.md'}
        records.append(record)
        cards.append(f'<section class="card"><h2>{html.escape(title)}</h2><div class="tag">'
            f'{html.escape(folder.name)} · {n_pages} 页 · {len(figures)} 幅图</div><div class="buttons">'
            f'<a href="{quote(record["html"])}">阅读中文译文</a><a href="{quote(record["markdown"])}">Markdown</a>'
            f'<a href="{quote(folder.name)}/原文提取.txt">提取原文</a></div></section>')
    total_pages, total_figures = sum(r['pages'] for r in records), sum(r['figures'] for r in records)
    content = f'<header><div class="sub">论文 / 中文翻译</div><h1>{html.escape(args.title)}</h1>'
    content += f'<div class="sub">{len(records)} 篇论文 · {total_pages} 页原文 · {total_figures} 幅独立图件</div></header>'
    content += '<main class="index"><p>按原文页码阅读译文，展开原页截图进行对照。图片、公式和显示资源均保存在本地。</p>'
    content += '<div class="cards">' + ''.join(cards) + '</div></main>'
    content += '<footer>原图保留英文标注，中文图注及标注释义见译文；作者、代码标识符、网址和其他专名保留原文。</footer>'
    (out / 'index.html').write_text(shell(args.title, content), encoding='utf-8')
    write_json(out / '翻译清单.json', records)
    print(f'Built {len(records)} papers, {total_pages} pages, {total_figures} figures: {out / "index.html"}')


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids = [], set()
    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key == 'id':
                self.ids.add(value)
            if key in {'src', 'href'} and value:
                self.links.append((tag, key, value))


def check(args):
    import pymupdf
    out = Path(args.out).resolve()
    errors, records = [], []
    papers = discover(out)
    for folder, info in papers:
        try:
            text = (folder / '中文逐句翻译.md').read_text(encoding='utf-8')
            split_translation(text, info['pages'])
            actual = {p.name for p in (folder / 'pages').glob('page-*.png')}
            expected = {f'page-{n:03}.png' for n in range(1, info['pages']+1)}
            if actual != expected:
                errors.append(f'{folder.name}: original-page screenshots do not match metadata')
            if not (folder / '原文提取.txt').exists():
                errors.append(f'{folder.name}: missing raw source text')
            rendered = folder / '中文阅读版.html'
            if not rendered.exists():
                errors.append(f'{folder.name}: missing HTML reader')
            crops = list((folder / 'figures').glob('*.png'))
            manifest = folder / 'figures/manifest.json'
            if crops and not manifest.exists():
                errors.append(f'{folder.name}: crops lack manifest')
            elif manifest.exists():
                items = json.loads(manifest.read_text(encoding='utf-8'))
                listed = [item['file'] for item in items]
                if set(listed) != {p.name for p in crops} or len(listed) != len(set(listed)):
                    errors.append(f'{folder.name}: crop files/manifest mismatch')
                for item in items:
                    if item.get('source_sha256') and item['source_sha256'] != info['source_sha256']:
                        errors.append(f'{folder.name}: crop source fingerprint mismatch')
            for image in list((folder / 'pages').glob('*.png')) + crops:
                pix = pymupdf.Pixmap(image)
                if pix.width < 1 or pix.height < 1:
                    errors.append(f'Empty image: {image}')
            records.append({'id': folder.name, 'pages': info['pages'],
                'figures': len(list((folder / 'figures').glob('figure-*.png')))})
        except (ValueError, KeyError, OSError) as exc:
            errors.append(f'{folder.name}: {exc}')
    if not (out / 'index.html').exists():
        errors.append('Missing library index.html')
    for current in out.rglob('*.html'):
        if '.work' in current.relative_to(out).parts:
            continue
        parser = LinkParser()
        parser.feed(current.read_text(encoding='utf-8'))
        for tag, key, link in parser.links:
            target = urlsplit(link)
            if target.scheme or target.netloc:
                if key == 'src' or tag == 'link':
                    errors.append(f'{current.name}: nonlocal reading resource {link}')
                continue
            if not target.path:
                if target.fragment and unquote(target.fragment) not in parser.ids:
                    errors.append(f'{current.name}: broken anchor {link}')
                continue
            path = (current.parent / unquote(target.path)).resolve()
            if not path.is_relative_to(out) or not path.exists():
                errors.append(f'{current.relative_to(out)}: missing or external local file {link}')
    css = out / 'assets/katex.min.css'
    if css.exists():
        for value in re.findall(r'url\(([^)]+)\)', css.read_text(encoding='utf-8')):
            font = value.strip('"\'')
            if not (css.parent / font).exists():
                errors.append(f'Missing formula font: {font}')
    result = {'structural_checks_passed': not errors, 'translation_semantics': 'requires source comparison',
              'papers': records, 'total_pages': sum(p['pages'] for p in records),
              'total_figures': sum(p['figures'] for p in records), 'errors': errors}
    write_json(out / '完整性检查.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise ValueError(f'{len(errors)} structural check(s) failed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare', help='Extract source text, page screenshots, blocks and metadata.')
    p.add_argument('--input', nargs='+', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--recursive', action='store_true')
    p.add_argument('--dpi', type=int, default=144)
    p.set_defaults(func=prepare)
    p = commands.add_parser('adopt', help='Register an existing paper folder without modifying translations.')
    p.add_argument('--pdf', required=True)
    p.add_argument('--paper', required=True)
    p.add_argument('--id')
    p.set_defaults(func=lambda a: print(json.dumps(register(Path(a.pdf).resolve(), Path(a.paper).resolve(), a.id), ensure_ascii=False)))
    p = commands.add_parser('crop', help='Render complete figure/table/equation crops from PDF coordinates.')
    p.add_argument('--pdf', required=True)
    p.add_argument('--paper', required=True)
    p.add_argument('--manifest', required=True)
    p.add_argument('--dpi', type=int, default=216)
    p.set_defaults(func=crop)
    p = commands.add_parser('build', help='Build offline reading pages from complete page-marked translations.')
    p.add_argument('--out', required=True)
    p.add_argument('--title', default='论文中文译文')
    p.set_defaults(func=build)
    p = commands.add_parser('check', help='Check page coverage, links, images, fonts, fences and crop manifests.')
    p.add_argument('--out', required=True)
    p.set_defaults(func=check)
    args = parser.parse_args()
    try:
        if hasattr(args, 'dpi') and not 36 <= args.dpi <= 600:
            raise ValueError('DPI must be between 36 and 600.')
        args.func(args)
    except (ValueError, KeyError, OSError, ImportError) as exc:
        parser.exit(2, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
