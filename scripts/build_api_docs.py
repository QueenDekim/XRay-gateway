"""Generate sectioned API Wiki pages and Markdown reference from one catalog."""
import html,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    pages=json.loads((ROOT/'gateway/api_reference.json').read_text(encoding='utf-8'))['pages']
    wiki=ROOT/'gateway/web/wiki';wiki.mkdir(exist_ok=True)
    docs=ROOT/'docs/api';docs.mkdir(exist_ok=True)
    catalog=json.loads((ROOT/'gateway/web/locales.json').read_text(encoding='utf-8'))
    def text(tag,pair):
        catalog[pair['ru']]=pair['en']
        return '<'+tag+' data-i18n="'+html.escape(pair['ru'],quote=True)+'">'+html.escape(pair['ru'])+'</'+tag+'>'
    for page in pages:
        parts=[text('h2',page['title'])];markdown=['# '+page['title']['en']]
        for paragraph in page['paragraphs']:parts.append(text('p',paragraph));markdown+=['',paragraph['en']]
        for index,endpoint in enumerate(page['endpoints']):
            identity=page['slug']+'-'+str(index+1);method=endpoint['method'];path=endpoint['path']
            parts.append('<section class="api-endpoint" id="'+identity+'"><h3><code>'+method+'</code> <code>'+html.escape(path)+'</code></h3><span class="api-role">'+endpoint['role']+'</span>')
            parts.append(text('p',endpoint['description']));markdown+=['','## '+method+' '+path,'','Role: `'+endpoint['role']+'`.','',endpoint['description']['en']]
            for key,pair in [('request',{'ru':'Запрос','en':'Request'}),('response',{'ru':'Ответ','en':'Response'})]:
                if key in endpoint:
                    payload=json.dumps(endpoint[key],ensure_ascii=False,indent=2)
                    parts.append(text('h4',pair)+'<pre><code>'+html.escape(payload)+'</code></pre>')
                    markdown+=['',pair['en']+':','','```json',payload,'```']
            parts.append('</section>')
        (wiki/(page['slug']+'.html')).write_text('\n'.join(parts)+'\n',encoding='utf-8')
        filename='README.md' if page['slug']=='start' else page['slug']+'.md'
        links=['[API index](README.md)'] if page['slug']!='start' else ['['+p['title']['en']+']('+p['slug']+'.md)' for p in pages if p['slug']!='start']
        (docs/filename).write_text('\n'.join(markdown)+'\n\n'+' · '.join(links)+'\n',encoding='utf-8')
    navigation=''.join('<a href="'+('/wiki' if p['slug']=='start' else '/wiki/'+p['slug'])+'" data-i18n="'+html.escape(p['title']['ru'],quote=True)+'">'+html.escape(p['title']['ru'])+'</a>' for p in pages)
    (ROOT/'gateway/web/pages/wiki.html').write_text('<section id="wikiPage" class="page"><div class="heading"><h1>API Wiki</h1></div><div class="wiki-layout"><nav class="wiki-navigation" aria-label="API Wiki">'+navigation+'</nav><article class="wiki-article">{{WIKI_CONTENT}}</article></div></section>\n',encoding='utf-8')
    (ROOT/'gateway/web/locales.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Generated '+str(len(pages))+' API Wiki sections and Markdown pages')

if __name__=='__main__':main()
