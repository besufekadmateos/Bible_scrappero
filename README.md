
# Multi-Language Bible Scraper (WordProject Engine)

A high-performance, robust, and multithreaded Python web scraper designed to extract complete text chapters and audio streaming links from WordProject. It automatically handles complex, shifting website layouts across different language translations and compiles them into isolated, optimized SQLite databases.

This data is ready to be directly plugged into applications like Telegram bots, mobile apps, or web APIs.

## ✨ Features

* **Dynamic Language Mapping:** Automatically crawls the main site index to discover and map available languages.
* **Smart Layout Adaptability:** Seamlessly transitions between inline span formats (like the English KJV layout) and block paragraph structures (like the Amharic Holy Bible layout).
* **Verse 1 Auto-Recovery:** Fixes a common web issue where Verse 1 lacks an explicit `<span class="verse">` or number marker, ensuring no leading text is left behind.
* **Red-Letter Text Protection:** Uses selective HTML element unwrapping to ensure chapters featuring Jesus's words highlighted in red (e.g., Matthew 6, John 15, Revelation) are fully scraped instead of skipped.
* **Multi-Threaded Concurrency:** Powered by a `ThreadPoolExecutor` loop for lightning-fast scraping without dropping server connections.
* **Fail-Safe Resume Engine:** Scans your local database before starting so you can pause and resume downloads right where you left off.

## 🛠️ Tech Stack & Requirements

* **Language:** Python 3.8+
* **Database:** SQLite3
* **Libraries:** * `requests` (Network operations)
    * `beautifulsoup4` (HTML parsing layout tree)

## 🚀 Installation & Setup
pip install requests beautifulsoup4
python bible.py

📖 How It Works
Select Language: Upon launching, the script queries the live WordProject mirror and lists all active languages. Type the number matching your targeted language.

Database Generation: The script creates a dedicated, sanitized database file (e.g., bible_Amharic_Holy_Bible.db or bible_English_Holy_Bible_-_KJV.db).

Automated Scraping: The multi-threaded engine maps out the testaments, books, and individual chapters, pouring text verses and corresponding .mp3 CDN audio paths straight into your database.

Important Notes
Rate Limiting: The scraper is pre-configured to run on 5 threads with a minor sleep delay to keep the server connection stable and avoid getting blocked. It is recommended to leave MAX_WORKERS = 5 unchanged.

To Re-download a Language: If you ever need to perform a completely fresh download of a translation, simply delete that translation's specific .db file from your directory and run the script again.

🤝 License
This project is intended strictly for educational, personal, and research development purposes. Please respect the terms of service of the content host.
