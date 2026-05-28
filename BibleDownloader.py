import os
import re
import time
import sqlite3
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.wordproject.org/"

# =====================================================================
# 1. BULLETPROOF DATABASE CONFIGURATION
# =====================================================================
def initialize_database(db_name="bible_factory.db"):
    """
    Creates an optimized SQLite database schema built for high-performance indexing.
    Includes ON CONFLICT REPLACE to make the crawler safe to restart or run repeatedly.
    """
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    
    # Core Verses Table with safety constraints
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bible_verses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            language TEXT,
            testament TEXT,
            book_number INTEGER,
            book_name TEXT,
            chapter INTEGER,
            verse_number INTEGER,
            verse_text TEXT,
            UNIQUE(language, book_number, chapter, verse_number) ON CONFLICT REPLACE
        )
    ''')
    
    # Chapter-level Media & Navigation Mapping Table with safety constraints
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chapter_audio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            language TEXT,
            book_number INTEGER,
            chapter INTEGER,
            audio_url TEXT,
            is_downloaded INTEGER DEFAULT 0,
            local_path TEXT,
            UNIQUE(language, book_number, chapter) ON CONFLICT REPLACE
        )
    ''')
    
    # High-Performance Indexes for instant execution on App / Bot queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_verses_lookup ON bible_verses (language, book_number, chapter, verse_number);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_audio_lookup ON chapter_audio (language, book_number, chapter);')
    
    conn.commit()
    return conn

# =====================================================================
# 2. WEB PARSING CORE LOGIC
# =====================================================================
def get_soup(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        if response.status_code == 200:
            return BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"\n   ⚠️ Connection warning for {url}: {e}")
    return None

def list_languages():
    print("🔄 Connecting to target servers to parse dynamic language layout...")
    soup = get_soup(BASE_URL + "index.htm")
    if not soup:
        return {}
        
    languages = {}
    lang_grid = soup.find('div', class_='ym-grid linearize-level-2')
    links = lang_grid.find_all('a') if lang_grid else soup.find_all('a', href=re.compile(r'^bibles/.*index\.htm$'))
    
    for link in links:
        url = link.get('href', '')
        if not url: continue
        full_url = BASE_URL + url if not url.startswith('http') else url
        raw_name = link.get_text(strip=True)
        
        bracket_match = re.search(r'\[(.*?)\]', raw_name)
        clean_name = bracket_match.group(1) if bracket_match else raw_name.split('[')[0].strip()
        
        if any(x in clean_name.upper() for x in ["CAN NOT FIND", "STUDY", "WITH ENGLISH TRANSLATION"]):
            continue
            
        if clean_name and full_url not in languages.values():
            languages[clean_name] = full_url
            
    return dict(sorted(languages.items()))

def fetch_books(lang_url):
    soup = get_soup(lang_url)
    if not soup: return []
        
    books = []
    content_area = (
        soup.find('div', class_='main') or 
        soup.find('div', id='main') or 
        soup.find('ul', class_='books') or
        soup.find('div', class_='ym-cbox')
    )
    
    book_links = content_area.find_all('a', href=re.compile(r'\d+/')) if content_area else soup.select('ul.nav-stacked li a, ul.books li a')

    for a in book_links:
        href = a.get('href', '').strip()
        book_name = a.get_text(strip=True)
        if not href or any(x in href for x in ['#', 'contact', 'wordproject', 'audio']): continue
            
        if href.endswith('index.htm') and not re.search(r'/\d+/index\.htm$|\d+/index\.htm$', href):
            if not re.search(r'\d+/|^\d+$', href): continue
                
        base_part = lang_url.rsplit('/', 1)[0] if lang_url.endswith('.htm') else lang_url.rstrip('/')
        full_book_url = href if href.startswith('http') else f"{base_part}/{href.lstrip('/')}"
            
        num_match = re.search(r'/(\d+)/', full_book_url)
        book_num = int(num_match.group(1)) if num_match else 0
        
        if book_name and not any(b['url'] == full_book_url for b in books):
            books.append({'name': book_name, 'url': full_book_url, 'num': book_num})
            
    return books

def fetch_chapters(book_url):
    soup = get_soup(book_url)
    if not soup: return []
        
    chapters = []
    current_chap = soup.select_one('span.chapread')
    if current_chap:
        chapters.append({'num': int(re.sub(r'[^\d]', '', current_chap.get_text(strip=True))), 'url': book_url})
    
    chap_area = (
        soup.find('p', class_='ym-noprint') or 
        soup.find('div', class_='chapters') or 
        soup.find('ul', class_='chapters') or
        soup.find('div', class_='main')
    )
    chapter_links = chap_area.find_all('a') if chap_area else soup.select('p.ym-noprint a.chap, div.chapters a')
    
    for a in chapter_links:
        href = a.get('href', '').split('#')[0].strip()
        if not href or 'contact' in href or 'wordproject' in href: continue
            
        base_part = book_url.rsplit('/', 1)[0] if book_url.endswith('.htm') else book_url.rstrip('/')
        full_chap_url = href if href.startswith('http') else f"{base_part}/{href.lstrip('/')}"
        
        try:
            chap_num = int(re.sub(r'[^\d]', '', a.get_text(strip=True)))
            if not any(c['num'] == chap_num for c in chapters):
                chapters.append({'num': chap_num, 'url': full_chap_url})
        except ValueError:
            continue
            
    return sorted(chapters, key=lambda x: x['num'])

def parse_verses_and_audio(chapter_url):
    soup = get_soup(chapter_url)
    if not soup: return [], None
        
    audio_url = None
    audio_elements = soup.find_all('a', href=re.compile(r'\.mp3$', re.IGNORECASE))
    for element in audio_elements:
        href = element.get('href', '').strip()
        if 'wordproaudio.net' in href or 'wordfree.net' in href:
            audio_url = href
            break
            
    if not audio_url:
        audio_match = re.search(r'(https?://[^\s"\']+(?:wordproaudio\.net|wordfree\.net)[^\s"\']+\.mp3)', str(soup), re.IGNORECASE)
        if audio_match: audio_url = audio_match.group(1)

    verses = []
    
    # Approach 1: Standard 'textBody' layout (Paragraph structure)
    text_body = soup.find('div', id='textBody') or soup.find('div', class_='textBody')
    if text_body:
        for extra in text_body.find_all(['h3', 'div', 'span.dimver']):
            extra.decompose()
        p_tags = text_body.find_all('p')
        v_idx = 1
        for p_tag in p_tags:
            raw_content = p_tag.get_text("|||", strip=True)
            lines = [line.strip() for line in raw_content.split("|||") if line.strip()]
            for line in lines:
                clean_text = re.sub(r'^\d+\s*[፤]?\s*', '', line).strip()
                match_num = re.match(r'^(\d+)', line)
                current_v_num = int(match_num.group(1)) if match_num else v_idx
                verses.append((current_v_num, clean_text))
                v_idx = current_v_num + 1
        if verses: return verses, audio_url

    # Approach 2: Direct span class extraction (Fallback for KJV / Oromoo inline structures)
    verse_spans = soup.find_all('span', class_='verse')
    if verse_spans:
        for span in verse_spans:
            v_str = span.get('id', '').strip() or re.sub(r'[^\d]', '', span.get_text(strip=True))
            try:
                v_num = int(v_str)
            except ValueError:
                continue
            
            next_node = span.next_sibling
            text_pieces = []
            while next_node:
                if next_node.name == 'span' and 'verse' in next_node.get('class', []): break
                if next_node.name != 'br':
                    text_pieces.append(next_node.get_text() if next_node.name else str(next_node))
                next_node = next_node.next_sibling
                
            v_text = re.sub(r'\s+', ' ', "".join(text_pieces)).strip()
            if v_text: verses.append((v_num, v_text))
            
    return verses, audio_url

# =====================================================================
# 3. EXTRACTION ROUTINE ENGINE
# =====================================================================
def main():
    db_conn = initialize_database()
    cursor = db_conn.cursor()
    
    langs = list_languages()
    if not langs:
        print("❌ Could not connect to language listing index mapping layout.")
        return
        
    lang_list = list(langs.keys())
    for idx, name in enumerate(lang_list):
        print(f"[{idx + 1}] {name}")
        
    while True:
        choice = input(f"\nSelect Language Channel Target (1-{len(lang_list)}): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(lang_list):
            selected_lang = lang_list[int(choice) - 1]
            lang_url = langs[selected_lang]
            break
        print("⚠️ Choice out of range.")

    print(f"\n🚀 Commencing target initialization download loop for: [{selected_lang}]")
    books = fetch_books(lang_url)
    if not books:
        print("❌ No index parameters extracted for books inside this target translation.")
        return

    print(f"📖 Discovered {len(books)} books inside channel directory structure. Scraping chapters...")
    
    total_chapters_processed = 0
    start_time = time.time()
    
    for b_idx, book in enumerate(books):
        testament = "Old" if 1 <= book['num'] <= 39 else "New"
        print(f"\n📂 Processing Book [{b_idx+1}/{len(books)}]: {book['name']} ({testament} Testament)")
        
        chapters = fetch_chapters(book['url'])
        if not chapters:
            print(f"   ⚠️ Skipping {book['name']} - No chapter indices resolved.")
            continue
            
        for chap in chapters:
            print(f"   ⚡ Scraping Chapter {chap['num']}... ", end="", flush=True)
            
            # Fetch data elements
            verses, audio_url = parse_verses_and_audio(chap['url'])
            
            if not verses:
                print(" [No text data resolved]")
                continue
                
            # Insert or Replace Text Rows
            for v_num, v_text in verses:
                cursor.execute('''
                    INSERT INTO bible_verses (language, testament, book_number, book_name, chapter, verse_number, verse_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (selected_lang, testament, book['num'], book['name'], chap['num'], v_num, v_text))
                
            # Insert or Replace Audio Tracking Link Rows
            if audio_url:
                cursor.execute('''
                    INSERT INTO chapter_audio (language, book_number, chapter, audio_url)
                    VALUES (?, ?, ?, ?)
                ''', (selected_lang, book['num'], chap['num'], audio_url))
                
            db_conn.commit()
            total_chapters_processed += 1
            print(f"Done ({len(verses)} verses saved) ✓")
            
            # Request throttle pause (Protects your scraping connection from blocking rules)
            time.sleep(0.4)

    db_conn.close()
    elapsed = time.time() - start_time
    print("\n" + "="*60)
    print("✨ EXTRACTION COMPLETE ✨")
    print("="*60)
    print(f"📦 Database Target: {total_chapters_processed} Chapters safely parsed/merged.")
    print(f"⏱️ Total Execution Duration: {elapsed/60:.2f} minutes.")
    print(f"📁 Output File Path: {os.path.abspath('bible_factory.db')}")
    print("="*60)

if __name__ == "__main__":
    main()