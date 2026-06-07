import os
import re
import time
import sqlite3
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://www.wordproject.org/"
MAX_WORKERS = 5  # Thread count optimized to prevent connection drops

# =====================================================================
# 1. DYNAMIC BULLETPROOF DATABASE CONFIGURATION
# =====================================================================
def initialize_database(language_name):
    """
    Creates an optimized SQLite database file uniquely named after the language selected.
    Includes ON CONFLICT REPLACE to make the crawler safe to restart or run repeatedly.
    """
    # Sanitize language name for filename
    safe_lang_name = re.sub(r'[^\w\-_]', '_', language_name)
    db_name = f"bible_{safe_lang_name}.db"
    
    conn = sqlite3.connect(db_name, check_same_thread=False)
    cursor = conn.cursor()
    
    # SQLite performance optimizations for high-speed multi-threaded writing
    cursor.execute('PRAGMA synchronous = OFF;')
    cursor.execute('PRAGMA journal_mode = WAL;')
    
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
    
    # Chapter-level Media Mapping Table
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
    
    # High-Performance Indexes for lightning-fast lookups
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_verses_lookup ON bible_verses (language, book_number, chapter, verse_number);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_audio_lookup ON chapter_audio (language, book_number, chapter);')
    
    conn.commit()
    return conn, db_name

# =====================================================================
# 2. WEB PARSING CORE LOGIC (Thread Safe Red-Letter Proof Extractor)
# =====================================================================
def get_soup(session, url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        response = session.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        if response.status_code == 200:
            return BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"\n    ⚠️ Connection warning for {url}: {e}")
    return None

def list_languages(session):
    print("🔄 Connecting to target servers to parse dynamic language layout...")
    soup = get_soup(session, BASE_URL + "index.htm")
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

def fetch_books(session, lang_url):
    soup = get_soup(session, lang_url)
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

def fetch_chapters(session, book_url):
    soup = get_soup(session, book_url)
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

def parse_verses_and_audio(session, chapter_url):
    """Clean, code-isolated Hybrid Extractor that handles Red-Letter elements safely."""
    soup = get_soup(session, chapter_url)
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
    text_body = soup.find('div', id='textBody') or soup.find('div', class_='textBody')
    
    if text_body:
        # 1. Strip out unwanted page layouts or formatting headers completely
        for element in text_body.find_all(['h3', 'div', 'a']):
            element.decompose()

        # 2. Process ALL spans safely without deleting text inside them
        for span in text_body.find_all('span'):
            classes = span.get('class', [])
            # Convert verse anchor numbers to plain strings
            if 'verse' in classes:
                v_num_str = re.sub(r'[^\d]', '', span.get_text())
                if v_num_str:
                    span.replace_with(f" {v_num_str} ")
            else:
                # CRITICAL PRESERVATION: Strip the red style wrapper tag, leaving text untouched!
                span.unwrap()

        # 3. Extract pure text strings entirely stripped of underlying HTML structural blocks
        raw_content = text_body.get_text(" ", strip=True)
        
        # 4. Parse strings using numeric anchors
        items = re.split(r'(\d+)\s*', raw_content)
        
        # If text occurs BEFORE the first numeral marker, it belongs to Verse 1
        if items and not items[0].strip().isdigit() and items[0].strip():
            clean_v1 = re.sub(r'^[፤፡\s[:punct:]<>]+', '', items[0]).strip()
            clean_v1 = re.sub(r'^.*?[:punct:]>\s*', '', clean_v1).strip()
            if clean_v1:
                verses.append((1, clean_v1))
        
        current_num = None
        for item in items:
            item = item.strip()
            if not item: continue
            
            if item.isdigit():
                current_num = int(item)
            else:
                clean_text = re.sub(r'^[፤፡\s[:punct:]<>]+', '', item).strip()
                clean_text = re.sub(r'^.*?[:punct:]>\s*', '', clean_text).strip()
                if clean_text and current_num is not None:
                    verses.append((current_num, clean_text))
                    current_num = None

    # Final protection data cleanup filter
    unique_verses = {}
    for v_num, v_text in verses:
        v_text = re.sub(r'<[^>]+>', '', v_text)
        v_text = v_text.replace('span class="verse"', '').replace('span', '').strip()
        
        if v_text:
            unique_verses[v_num] = v_text
            
    sorted_verses = sorted([(k, v) for k, v in unique_verses.items()], key=lambda x: x[0])
    return sorted_verses, audio_url

# =====================================================================
# 3. WORKER FUNCTION FOR MULTI-THREADING
# =====================================================================
def scrape_single_chapter(session, selected_lang, testament, book_num, book_name, chap_num, chap_url):
    """Worker task executed concurrently by threads."""
    try:
        verses, audio_url = parse_verses_and_audio(session, chap_url)
        return {
            'status': 'success', 'book_name': book_name, 'chap_num': chap_num,
            'verses': verses, 'audio_url': audio_url,
            'meta': (selected_lang, testament, book_num, book_name, chap_num)
        }
    except Exception as e:
        return {'status': 'error', 'url': chap_url, 'error': str(e)}

# =====================================================================
# 4. EXTRACTION ROUTINE ENGINE (WITH RESUME LOGIC)
# =====================================================================
def main():
    session = requests.Session()
    
    langs = list_languages(session)
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

    # Initialize dynamic database file
    db_conn, target_db_file = initialize_database(selected_lang)
    cursor = db_conn.cursor()

    # --- RESUME SYSTEM CHECK ---
    print("🔍 Inspecting local database cache to calculate bookmark resume points...")
    cursor.execute('''
        SELECT book_number, chapter 
        FROM bible_verses 
        WHERE language = ? 
        GROUP BY book_number, chapter
    ''', (selected_lang,))
    
    completed_chapters = {(row[0], row[1]) for row in cursor.fetchall()}
    if completed_chapters:
        print(f"✅ Found {len(completed_chapters)} chapters already completed in your database. Skipping those!")
    else:
        print("ℹ️ No previous footprint found. Starting a fresh download run.")

    print(f"\n🚀 Commencing target initialization download loop for: [{selected_lang}]")
    books = fetch_books(session, lang_url)
    if not books:
        print("❌ No index parameters extracted for books inside this target translation.")
        db_conn.close()
        return

    print(f"📖 Discovered {len(books)} books inside channel directory structure. Mapping chapters...")
    
    scraping_tasks = []
    skipped_count = 0
    
    for b_idx, book in enumerate(books):
        testament = "Old" if 1 <= book['num'] <= 39 else "New"
        chapters = fetch_chapters(session, book['url'])
        for chap in chapters:
            if (book['num'], chap['num']) in completed_chapters:
                skipped_count += 1
                continue
                
            scraping_tasks.append({
                'testament': testament, 'book_num': book['num'], 
                'book_name': book['name'], 'chap_num': chap['num'], 'chap_url': chap['url']
            })

    if skipped_count > 0:
        print(f"⏭️ Fast-forwarded past {skipped_count} chapters already archived.")

    total_tasks = len(scraping_tasks)
    if total_tasks == 0:
        print("\n🎉 Everything is already fully scraped and up to date!")
        db_conn.close()
        return

    print(f"⚡ Queue prepared with {total_tasks} remaining chapters. Launching parallel engine ({MAX_WORKERS} threads)...")

    total_chapters_processed = 0
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_chapter = {
            executor.submit(
                scrape_single_chapter, session, selected_lang, task['testament'], 
                task['book_num'], task['book_name'], task['chap_num'], task['chap_url']
            ): task for task in scraping_tasks
        }
        
        for future in as_completed(future_to_chapter):
            result = future.result()
            
            if result['status'] == 'error':
                print(f"  ❌ Error fetching data: {result['url']} | Reason: {result['error']}")
                continue
                
            verses = result['verses']
            audio_url = result['audio_url']
            selected_lang, testament, book_num, book_name, chap_num = result['meta']
            
            if not verses:
                print(f"   ⚠️ {book_name} Chapter {chap_num}: No text data resolved.")
                continue

            # Write batch chapter data
            for v_num, v_text in verses:
                cursor.execute('''
                    INSERT INTO bible_verses (language, testament, book_number, book_name, chapter, verse_number, verse_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (selected_lang, testament, book_num, book_name, chap_num, v_num, v_text))
                
            if audio_url:
                cursor.execute('''
                    INSERT INTO chapter_audio (language, book_number, chapter, audio_url)
                    VALUES (?, ?, ?, ?)
                ''', (selected_lang, book_num, chap_num, audio_url))
            
            db_conn.commit()
            total_chapters_processed += 1
            
            print(f"📥 Saved: {book_name} Chapter {chap_num} ({len(verses)} verses) [{total_chapters_processed}/{total_tasks}]")
            time.sleep(0.05)

    db_conn.close()
    elapsed = time.time() - start_time
    print("\n" + "="*60)
    print("✨ EXTRACTION COMPLETE ✨")
    print("="*60)
    print(f"📦 Database Target: {total_chapters_processed} New Chapters safely written.")
    print(f"⏱️ Total Execution Duration: {elapsed/60:.2f} minutes.")
    print(f"📁 Output File Path: {os.path.abspath(target_db_file)}")
    print("="*60)

if __name__ == "__main__":
    main()