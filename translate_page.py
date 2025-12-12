import sys
import os
import argparse
import time
import requests
import re
import json
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import html2text
import google.generativeai as genai
import markdown

# --- 設定 ---
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = 'gemini-2.0-flash'
OUTPUT_DIR = "translated_site"
CSS_FILENAME = "style.css"
CHUNK_SIZE = 12000

# ★CSS変更点: codeタグの背景色を削除(transparent)にしました
RAW_CSS = """
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.6;
    padding: 20px;
    max-width: 96%;
    margin: 0 auto;
    color: #333;
    background-color: #f9f9f9;
}
h1 { border-bottom: 2px solid #eaecef; padding-bottom: .3em; }
h2 { border-bottom: 1px solid #eaecef; padding-bottom: .3em; margin-top: 24px; }
table {
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
    overflow-x: auto;
    display: block;
}
th, td {
    border: 1px solid #dfe2e5;
    padding: 6px 13px;
    min-width: 100px;
}
th { background-color: #f6f8fa; font-weight: bold; }
tr:nth-child(2n) { background-color: #f6f8fa; }

img, svg {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 1em 0;
}
text, tspan {
    font-family: sans-serif;
}

/* ★修正: コードの背景色を透明にして、選択範囲っぽく見えるのを防ぐ */
code {
    background-color: transparent; /* 元は #f0f0f0 */
    padding: 0.2em 0; /* 横のパディングも削除して自然なテキストに */
    border-radius: 0;
    font-family: Consolas, "Courier New", monospace;
    font-weight: bold; /* 代わりに太字にして区別する */
    color: #d63384;    /* アクセントカラーをつける（お好みで削除可） */
}
/* 通常のテキストカラーに戻したい場合は color: inherit; にしてください */

pre {
    background-color: #f6f8fa;
    padding: 16px;
    overflow: auto;
    border-radius: 6px;
}
pre code {
    /* preの中のcode（ブロックコード）は色を変えない */
    color: inherit;
    background-color: transparent;
}

a { color: #0366d6; text-decoration: none; }
a:hover { text-decoration: underline; }

@media (prefers-color-scheme: dark) {
    body { background-color: #0d1117; color: #c9d1d9; }
    th { background-color: #161b22; border-color: #30363d; }
    td { border-color: #30363d; }
    tr:nth-child(2n) { background-color: #161b22; }
    
    /* ダークモード時のコード背景も透明に */
    code { 
        background-color: transparent; 
        color: #ff7b72; /* ダークモード用のアクセントカラー */
    }
    pre { background-color: #161b22; }
    pre code { color: inherit; }

    h1, h2 { border-color: #21262d; }
    a { color: #58a6ff; }
    
    img, svg {
        background-color: white;
        padding: 10px;
        border-radius: 4px;
    }
}
"""

if not API_KEY:
    print("エラー: 環境変数 GEMINI_API_KEY が設定されていません。")
    sys.exit(1)

genai.configure(api_key=API_KEY)

def setup_css_file():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    css_path = os.path.join(OUTPUT_DIR, CSS_FILENAME)
    with open(css_path, 'w', encoding='utf-8') as f:
        f.write(RAW_CSS)

def get_html(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"  [Error] ページ取得失敗: {url} ({e})")
        return None

def get_save_path_base(url):
    parsed = urlparse(url)
    path = parsed.path.lstrip('/')
    if not path or path.endswith('/'):
        path += 'index'
    if path.endswith('.html'):
        path = path[:-5]
    return os.path.join(OUTPUT_DIR, parsed.netloc, path)

def download_and_process_image(img_tag, base_url, current_html_dir):
    src = img_tag.get('src')
    if not src: return
    img_abs_url = urljoin(base_url, src)
    parsed_img = urlparse(img_abs_url)
    img_save_rel_path = os.path.join(parsed_img.netloc, parsed_img.path.lstrip('/'))
    img_save_full_path = os.path.join(OUTPUT_DIR, img_save_rel_path)

    if not os.path.exists(img_save_full_path):
        try:
            os.makedirs(os.path.dirname(img_save_full_path), exist_ok=True)
            resp = requests.get(img_abs_url, timeout=10)
            resp.raise_for_status()
            with open(img_save_full_path, 'wb') as f:
                f.write(resp.content)
        except Exception as e:
            print(f"    [Image Error] {src}: {e}")
            return

    rel_path_for_html = os.path.relpath(img_save_full_path, start=current_html_dir)
    rel_path_for_html = rel_path_for_html.replace(os.sep, '/')
    img_tag['src'] = rel_path_for_html
    if img_tag.has_attr('srcset'): del img_tag['srcset']

def translate_list_batch(text_list):
    if not text_list: return []
    json_text = json.dumps(text_list, ensure_ascii=False)
    
    model = genai.GenerativeModel(MODEL_NAME)
    prompt = f"""
あなたはx86アセンブリ言語の専門家です。
以下のJSONリストに含まれる技術用語や短いフレーズを日本語に翻訳してください。
# 制約
1. 入力と同じ長さのJSONリストを出力してください。
2. 順番を変えないでください。
3. ニーモニックや数値はそのままにしてください。
4. JSON形式のみを出力してください。
# 入力
{json_text}
    """
    try:
        response = model.generate_content(prompt)
        cleaned = response.text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r'^```(?:json)?\s*|\s*```$', '', cleaned)
        translated_list = json.loads(cleaned)
        if len(translated_list) != len(text_list):
            return text_list
        return translated_list
    except Exception as e:
        print(f"    [Error] SVGテキスト翻訳失敗: {e}")
        return text_list

def process_and_translate_svgs(soup):
    svgs = soup.find_all('svg')
    if not svgs: return
    print(f"  [Info] SVG画像の内部テキストを翻訳中 ({len(svgs)}個)...")

    for i, svg in enumerate(svgs):
        target_nodes = []
        original_texts = []
        for text_tag in svg.find_all(['text', 'tspan']):
            if text_tag.string and text_tag.string.strip():
                target_nodes.append(text_tag)
                original_texts.append(text_tag.string.strip())
        
        if not original_texts: continue
        translated_texts = translate_list_batch(original_texts)
        for node, trans_text in zip(target_nodes, translated_texts):
            node.string.replace_with(trans_text)

def convert_to_hybrid_md(html_content, base_url):
    soup = BeautifulSoup(html_content, 'html.parser')
    for element in soup(['script', 'style', 'nav', 'footer']):
        element.decompose()

    current_base_path = get_save_path_base(base_url)
    current_page_dir = os.path.dirname(current_base_path)

    extracted_links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        full_url = urljoin(base_url, href)
        parsed_base = urlparse(base_url)
        parsed_target = urlparse(full_url)
        if parsed_base.netloc == parsed_target.netloc and '/x86/' in parsed_target.path and '#' not in href: 
            extracted_links.append(full_url)

    for a in soup.find_all('a', href=True):
        href = a['href']
        full_target_url = urljoin(base_url, href)
        parsed_base = urlparse(base_url)
        parsed_target = urlparse(full_target_url)
        if parsed_base.netloc == parsed_target.netloc and '/x86/' in parsed_target.path:
            target_base_path = get_save_path_base(full_target_url)
            rel_path = os.path.relpath(target_base_path, start=current_page_dir)
            rel_path = rel_path.replace(os.sep, '/')
            new_href = f"{rel_path}.html"
            if parsed_target.fragment:
                new_href += f"#{parsed_target.fragment}"
            a['href'] = new_href

    for img in soup.find_all('img'):
        download_and_process_image(img, base_url, current_page_dir)

    process_and_translate_svgs(soup)

    protected_tags = {}
    for i, table in enumerate(soup.find_all('table')):
        pid = f"__TABLE_PLACEHOLDER_{i}__"
        raw_html = str(table)
        raw_html = raw_html.replace('</tr>', '</tr>\n').replace('</thead>', '</thead>\n').replace('</tbody>', '</tbody>\n')
        protected_tags[pid] = raw_html
        table.replace_with(pid)

    for i, img in enumerate(soup.find_all('img')):
        pid = f"__IMG_PLACEHOLDER_{i}__"
        protected_tags[pid] = str(img)
        img.replace_with(pid)

    for i, svg in enumerate(soup.find_all('svg')):
        pid = f"__SVG_PLACEHOLDER_{i}__"
        protected_tags[pid] = str(svg)
        svg.replace_with(pid)

    h = html2text.HTML2Text()
    h.ignore_links = False
    h.body_width = 0
    h.ignore_images = True
    markdown_content = h.handle(str(soup.body))

    for pid, raw_html in protected_tags.items():
        markdown_content = markdown_content.replace(pid, raw_html)

    return markdown_content, extracted_links

def clean_model_output(text):
    if not text: return ""
    lines = text.strip().split('\n')
    start_idx = 0
    for i, line in enumerate(lines):
        l = line.strip()
        if l.startswith('#') or l.startswith('<') or l.startswith('|') or l.startswith('```'):
            start_idx = i
            break
        if re.match(r'^(Here|Sure|Okay|The following|Translation|Part)', l, re.IGNORECASE):
            continue
        if not l: continue
        start_idx = i
        break
    lines = lines[start_idx:]
    if not lines: return ""
    if lines[0].strip().startswith("```"):
        lines.pop(0)
        if lines and lines[-1].strip() == "```": lines.pop()
    return '\n'.join(lines)

def split_text_by_tags(text, limit):
    delimiter_pattern = re.compile(r'(</tr>|</table>|</thead>|</tbody>|</div>|</p>|</svg>|</text>|\n)')
    tokens = delimiter_pattern.split(text)
    chunks = []
    current_chunk = []
    current_length = 0
    for token in tokens:
        if not token: continue
        token_len = len(token)
        if token_len > limit and current_length == 0:
            chunks.append(token)
            continue
        if current_length + token_len > limit:
            chunks.append(''.join(current_chunk))
            current_chunk = [token]
            current_length = token_len
        else:
            current_chunk.append(token)
            current_length += token_len
    if current_chunk:
        chunks.append(''.join(current_chunk))
    return chunks

def translate_content(content, title):
    model = genai.GenerativeModel(MODEL_NAME)
    
    if len(content) <= CHUNK_SIZE:
        chunks = [content]
    else:
        print(f"  [Info] 分割翻訳: {len(content)}文字 -> {len(content)//CHUNK_SIZE + 1}分割")
        chunks = split_text_by_tags(content, CHUNK_SIZE)
    
    final_result = []
    
    for i, chunk in enumerate(chunks):
        if len(chunks) > 1:
            print(f"    - パート {i+1}/{len(chunks)} を翻訳中...")
        
        prompt = f"""
あなたはx86アセンブリ言語の専門家です。
以下のテキスト（MarkdownとHTMLが混在）を日本語に翻訳してください。

これは非常に長いドキュメントを分割したパート{i+1}です。
入力がHTMLタグの途中（例: `<tr>`や`<td>`の中）で始まったり終わったりする可能性があります。

# 重要: 厳守事項
1. **タグの自動補完をしない**: 入力にあるタグのみを出力してください。
2. **構造を維持**: HTML構造はいじらないでください。
3. **プレースホルダー維持**: `__SVG_PLACEHOLDER_x__` などの文字列は絶対に削除・変更しないでください。
4. **挨拶不要**: 翻訳結果のみを出力してください。
5. **Markdown形式を維持**: コードブロックで囲まないでください。

# 翻訳対象
{chunk}
        """
        
        max_retries = 3
        chunk_success = False
        for attempt in range(max_retries):
            try:
                response = model.generate_content(prompt)
                cleaned_text = clean_model_output(response.text)
                final_result.append(cleaned_text)
                chunk_success = True
                break
            except Exception as e:
                if "429" in str(e):
                    print(f"    [Wait] API制限。10秒待機... ({attempt+1}/{max_retries})")
                    time.sleep(10)
                else:
                    print(f"    [Error] API翻訳失敗: {e}")
                    final_result.append(chunk) 
                    chunk_success = True
                    break
        if not chunk_success:
            final_result.append(chunk)
        time.sleep(1)

    return ''.join(final_result)

def save_files(url, md_content, suffix=""):
    base_path = get_save_path_base(url)
    directory = os.path.dirname(base_path)
    if not os.path.exists(directory):
        os.makedirs(directory)

    md_filename = f"{base_path}{suffix}.md"
    with open(md_filename, 'w', encoding='utf-8') as f:
        f.write(md_content)

    html_filename = f"{base_path}{suffix}.html"
    html_body = markdown.markdown(md_content, extensions=['fenced_code'])
    html_body = re.sub(r'<([A-Z0-9][A-Z0-9_:-]*)>', r'&lt;\1&gt;', html_body)

    css_abs_path = os.path.abspath(os.path.join(OUTPUT_DIR, CSS_FILENAME))
    html_dir_abs_path = os.path.abspath(directory)
    relative_css_path = os.path.relpath(css_abs_path, start=html_dir_abs_path)
    relative_css_path = relative_css_path.replace(os.sep, '/')

    full_html = f"""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{os.path.basename(base_path)}{suffix}</title>
    <link rel="stylesheet" href="{relative_css_path}">
</head>
<body>
    {html_body}
</body>
</html>
    """
    
    with open(html_filename, 'w', encoding='utf-8') as f:
        f.write(full_html)
    
    label = "原文(EN)" if suffix else "翻訳(JP)"
    print(f"  -> {label}保存完了: {html_filename}")

def process_url(url, is_recursive=False, visited=None):
    if visited is not None and url in visited:
        return [], False

    base_path = get_save_path_base(url)
    html_path = f"{base_path}.html"
    
    if os.path.exists(html_path):
        print(f"\n[スキップ] 翻訳済み: {url}")
        html = get_html(url)
        if not html: return [], False
        _, links = convert_to_hybrid_md(html, url)
        if visited is not None: visited.add(url)
        return links, False

    print(f"\n[処理開始] {url}")
    html = get_html(url)
    if not html: return [], False

    # 1. 英語のままMD化（画像DLやSVG翻訳はここに含まれる）
    md_content_en, links = convert_to_hybrid_md(html, url)
    
    # 2. 原文保存
    save_files(url, md_content_en, suffix="_en")
    
    # 3. 日本語へ翻訳
    translated_md = translate_content(md_content_en, url)
    
    was_translated = False
    if translated_md:
        # 4. 翻訳文保存
        save_files(url, translated_md, suffix="")
        if visited is not None: visited.add(url)
        was_translated = True
    
    return links, was_translated

def main():
    parser = argparse.ArgumentParser(description='x86リファレンス 翻訳ツール (完成版)')
    parser.add_argument('url', type=str, help='開始URL')
    parser.add_argument('--limit', type=int, default=5, help='新規翻訳ページ数上限')
    args = parser.parse_args()

    setup_css_file()

    start_url = args.url
    max_new_translations = args.limit
    
    visited = set()
    queue = [start_url]
    new_translated_count = 0

    while queue:
        if max_new_translations > 0 and new_translated_count >= max_new_translations:
            print("\n[Info] 上限に達したため終了します。")
            break

        current_url = queue.pop(0)
        current_url_clean = current_url.rstrip('/')
        if any(v.rstrip('/') == current_url_clean for v in visited):
            continue

        found_links, was_translated = process_url(current_url, visited=visited)
        
        if was_translated:
            new_translated_count += 1
            print(f"  (進捗: {new_translated_count}/{max_new_translations}) ...待機中(2秒)...")
            time.sleep(2)
        
        for link in found_links:
            if link not in queue and not any(v.rstrip('/') == link.rstrip('/') for v in visited):
                queue.append(link)

if __name__ == "__main__":
    main()