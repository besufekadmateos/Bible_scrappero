
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
