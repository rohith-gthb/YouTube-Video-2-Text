# Transcribe.Pro 🎙️🎥
### High-Speed YouTube Transcript Extractor & Batch Downloader

Transcribe.Pro is a professional grade web application designed to extract, clean, and export YouTube transcripts at scale. Whether you need a single video's script or the entire content of a massive playlist, Transcribe.Pro handles it with high speed and reliability using rotating residential proxies.

---

## ✨ Key Features

- **⚡ 5x Speed Concurrency:** Process up to 5 videos simultaneously in Batch mode.
- **📂 Playlist & Channel Support:** Extract video lists directly from any YouTube channel or playlist URL.
- **📊 Live UI Progress:** Real-time progress bar (0% → 100%) for background batch jobs.
- **🧠 Smart URL Detection:** Automatically switches between "Video" and "Batch" modes based on the link you paste.
- **🌪️ Proxy Rotation:** Uses Webshare residential proxies to bypass YouTube's IP-based rate limits.
- **📥 Multiple Formats:** Export transcripts as `.txt`, `.csv`, `.md`, or `.json`.
- **⌨️ Keyboard Optimized:** Support for "Enter" key extraction for efficiency.

---

## 🛠️ Technical Stack

- **Backend:** FastAPI (Python), `youtube-transcript-api`, `asyncio`, `uvicorn`.
- **Frontend:** HTML5, TailwindCSS (Vanilla JS), Grid/Flex layouts.
- **IP Protection:** Rotating Residential Proxies + User-Agent rotation.
- **Concurrency:** `asyncio.Semaphore` + `BackgroundTasks`.

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.10+
- Browser (Chrome/Firefox/Safari)

### 2. Setup
Clone the repository and run the setup script:
```bash
# Make start script executable
chmod +x start.sh

# Run the unified start script (it handles venv and servers)
./start.sh
```

### 3. Usage
- **Video Mode:** Paste a single URL and hit Enter.
- **Batch Mode:** Paste a Channel or Playlist link. The app will auto-switch modes. Use the selection grid to choose which videos to download.

---

## 🔧 Environment Variables (.env)
Create a `.env` file in the `backend/` directory for proxy credentials:
```env
WEBSHARE_USER=your_username
WEBSHARE_PASS=your_password
```

---

## 🏛️ License
All rights reserved. Not affiliated with YouTube.
