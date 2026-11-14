"""Authenticated document routes and safe shared page rendering."""
import html,json,re
from pathlib import Path
from urllib.parse import urlsplit

PAGES={'overview':'Обзор','profiles':'Профили','iplists':'IP-списки','routeros':'RouterOS','settings':'Настройки','account':'Моя учётная запись','wiki':'API Wiki'}
WIKI_TOPICS={'start','authentication','profiles','ip-lists','routeros','terminal','accounts','settings','updates'}


def route(path):
    if path in ['/'+key for key in PAGES]:return path[1:],None
    if path.startswith('/wiki/') and path[6:] in WIKI_TOPICS:return 'wiki',path[6:]
    return None,None


def safe_next(value):
    parsed=urlsplit(value or '')
    if parsed.scheme or parsed.netloc or parsed.query or not route(parsed.path)[0]:return '/overview'
    fragment=('#'+parsed.fragment) if re.fullmatch(r'[a-z-]{1,40}',parsed.fragment) else ''
    return parsed.path+fragment


def render(assets,page,state,topic=None):
    assets=Path(assets)
    if page=='login':return (assets/'pages/login.html').read_bytes()
    content=(assets/'pages'/(page+'.html')).read_text(encoding='utf-8')
    if page=='wiki':
        content=content.replace('{{WIKI_CONTENT}}',(assets/'wiki'/((topic or 'start')+'.html')).read_text(encoding='utf-8'))
        href='/wiki' if not topic or topic=='start' else '/wiki/'+topic
        content=content.replace('<a href="'+href+'"','<a aria-current="page" href="'+href+'"',1)
    source=(assets/'index.html').read_text(encoding='utf-8')
    source=source.replace('{{PAGE_CONTENT}}',content).replace('{{PAGE_NAME}}',page)
    source=source.replace('{{PAGE_STATE}}',json.dumps(state,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026'))
    source=source.replace('<span id="pageName" data-i18n="Обзор">Обзор</span>','<span id="pageName" data-i18n="'+PAGES[page]+'">'+PAGES[page]+'</span>')
    source=source.replace(' class="active"','')
    source=re.sub(r'(<a[^>]*data-page="'+page+r'"[^>]*)(>)',r'\1 class="active" aria-current="page"\2',source)
    if state['user']['role']=='admin':source=re.sub(r'(<a[^>]*id="routerNav"[^>]*?) hidden',r'\1',source)
    else:source=source.replace('id="settingsToggle"','id="settingsToggle" hidden')
    return source.encode()
