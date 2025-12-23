import re
import traceback
import json
import os
import random
import requests
import time
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException, Query, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from youtube_transcript_api.proxies import WebshareProxyConfig
from dotenv import load_dotenv
from ExtractUrls import extract_channel_videos
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import asyncio
import zipfile
import io
import http.cookiejar

# Load environment variables
load_dotenv()

# List of common browser User-Agents for rotation
# USER_AGENTS = [
#     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
#     "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
#     "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
#     "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
#     "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
#     "Mozilla/5.0 (AppleScript; Macintosh) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
# ]

# List of common browser User-Agents for rotation
USER_AGENTS = [
    # Chrome on Windows 10
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 Firefox/124.0",
    
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0"
]



def get_random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
    }

# Standard Global instance (use with caution, per-request config preferred)
ytt_api = YouTubeTranscriptApi()

# Global state for background jobs
# { "batch_id": { "status": "processing", "progress": 0, "total": 0, "completed": 0, "zip_data": None, "format": "txt", "error": None } }
active_batches = {}

# Proxy and Cookie logic
WEBSHARE_USER = os.getenv("WEBSHARE_USER")
WEBSHARE_PASS = os.getenv("WEBSHARE_PASS")

def get_webshare_config():
    """Returns a WebshareProxyConfig object for rotating residential proxies."""
    return WebshareProxyConfig(
        proxy_username=WEBSHARE_USER,
        proxy_password=WEBSHARE_PASS,
        filter_ip_locations=["US", "GB", "DE"]
    )

def get_rotating_proxy_dict():
    """Returns a proxy dict for 'requests' using Webshare rotating residential endpoint."""
    proxy_url = f"http://{WEBSHARE_USER}-rotate:{WEBSHARE_PASS}@p.webshare.io:80"
    return {"http": proxy_url, "https": proxy_url}

# Cookie file path
COOKIE_FILE = os.path.join(os.path.dirname(__file__), "cookies.txt")

def get_cookies():
    """Returns the cookie file path if it exists, otherwise None."""
    if os.path.exists(COOKIE_FILE):
        return COOKIE_FILE
    return None

def format_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{str(h) + ':' if h > 0 else ''}{str(m).zfill(2)}:{str(s).zfill(2)}"

# Setup Rate Limiting
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="YouTube Transcript API")

def clean_transcript_text(text: str) -> str:
    # Robust cleaning: Remove '>>', '>>>', [Music], (Laughter), etc.
    text = text.replace("&gt;&gt;", "").replace("&gt;", "")
    text = re.sub(r'>>+', '', text) 
    text = re.sub(r'\[.*?\]', '', text) 
    text = re.sub(r'\(.*?\)', '', text) 
    return text.strip()

def get_formatted_content(video_title: str, video_url: str, segments: List[Dict], format_type: str, include_timestamps: bool) -> str:
    """
    Unified formatter for all export types.
    """
    if format_type == 'json':
        return json.dumps({
            "title": video_title,
            "url": video_url,
            "transcript": segments
        }, indent=2)

    if format_type == 'csv':
        headers = "Start,Duration,Text" if include_timestamps else "Sentence"
        rows = []
        if include_timestamps:
            for s in segments:
                clean_text = s['text'].replace('"', '""')
                rows.append(f"{s['start']},{s['duration']},\"{clean_text}\"")
        else:
            full_text = " ".join([s['text'] for s in segments])
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', full_text) if s.strip()]
            for s in sentences:
                clean_sentence = s.replace('"', '""')
                rows.append(f"\"{clean_sentence}\"")
        return f"{headers}\n" + "\n".join(rows)

    if format_type == 'md':
        content = f"# {video_title}\n\nURL: {video_url}\n\nGenerated by Transcribe.Pro\n\n"
        if include_timestamps:
            for s in segments:
                content += f"**{format_time(s['start'])}**: {s['text']}\n\n"
        else:
            full_text = " ".join([s['text'] for s in segments])
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', full_text) if s.strip()]
            content += "\n\n".join([f"> {s}" for s in sentences])
        return content

    # Default to TXT
    if include_timestamps:
        return "\n".join([f"[{format_time(s['start'])}] {s['text']}" for s in segments])
    else:
        full_text = " ".join([s['text'] for s in segments])
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', full_text) if s.strip()]
        return "\n".join(sentences)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Environment-based CORS
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Removed buggy get_random_proxy as get_rotating_proxy_dict is already available and more stable.


def extract_video_id(url: str) -> Optional[str]:
    """Extracts the video ID from a YouTube URL."""
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
        r"youtu\.be\/([0-9A-Za-z_-]{11})",
        r"embed\/([0-9A-Za-z_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_video_info(video_id: str):
    """Fetches video metadata using requests and BeautifulSoup (Safer Alternative)."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    proxies = get_rotating_proxy_dict()
    
    try:
        response = requests.get(url, headers=get_random_headers(), proxies=proxies, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract title
        title = ""
        title_tag = soup.find("meta", property="og:title")
        if title_tag:
            title = title_tag["content"]
        
        # Extract thumbnail
        thumbnail = ""
        thumbnail_tag = soup.find("meta", property="og:image")
        if thumbnail_tag:
            thumbnail = thumbnail_tag["content"]
            
        # Extract author
        author = ""
        author_tag = soup.find("link", itemprop="name")
        if author_tag:
            author = author_tag["content"]
        elif soup.find("span", itemprop="author"):
            author = soup.find("span", itemprop="author").find("link", itemprop="name")["content"]

        return {
            "title": title or "Unknown Title",
            "thumbnail": thumbnail or f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            "author": author or "Unknown Author",
        }
    except Exception as e:
        print(f"Error fetching metadata: {e}")
        return None

def format_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{str(h) + ':' if h > 0 else ''}{str(m).zfill(2)}:{str(s).zfill(2)}"

def get_formatted_content(video_title: str, video_url: str, segments: List[Dict], format_type: str, include_timestamps: bool) -> str:
    """
    Unified formatter for all export types.
    """
    if format_type == 'json':
        return json.dumps({
            "title": video_title,
            "url": video_url,
            "transcript": segments
        }, indent=2)

    if format_type == 'csv':
        headers = "Start,Duration,Text" if include_timestamps else "Sentence"
        rows = []
        if include_timestamps:
            for s in segments:
                clean_text = s['text'].replace('"', '""')
                rows.append(f"{s['start']},{s['duration']},\"{clean_text}\"")
        else:
            full_text = " ".join([s['text'] for s in segments])
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', full_text) if s.strip()]
            for s in sentences:
                clean_sentence = s.replace('"', '""')
                rows.append(f"\"{clean_sentence}\"")
        return f"{headers}\n" + "\n".join(rows)

    if format_type == 'md':
        content = f"# {video_title}\n\nURL: {video_url}\n\nGenerated by Transcribe.Pro\n\n"
        if include_timestamps:
            for s in segments:
                content += f"**{format_time(s['start'])}**: {s['text']}\n\n"
        else:
            full_text = " ".join([s['text'] for s in segments])
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', full_text) if s.strip()]
            content += "\n\n".join([f"> {s}" for s in sentences])
        return content

    # Default to TXT
    if include_timestamps:
        return "\n".join([f"[{format_time(s['start'])}] {s['text']}" for s in segments])
    else:
        full_text = " ".join([s['text'] for s in segments])
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', full_text) if s.strip()]
        return "\n".join(sentences)

@app.get("/transcript")
@limiter.limit("5/minute")
async def get_transcript(request: Request, url: str = Query(..., description="The YouTube video URL")):
    video_id = extract_video_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    video_info = get_video_info(video_id)
    if not video_info:
        # Fallback to basic info if scraping fails but video ID is valid
        video_info = {
            "title": "YouTube Video",
            "thumbnail": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            "author": "YouTube"
        }

    for attempt in range(3):
        try:
            proxy_config = get_webshare_config()
            print(f"Using Webshare Residential Rotation (Attempt {attempt+1}) for {video_id}")
            
            # Create fresh API instance with our config
            api = YouTubeTranscriptApi(proxy_config=proxy_config)
            transcript_list = api.fetch(video_id)
            break # Success
        except (TranscriptsDisabled, NoTranscriptFound) as e:
            # Fatal errors, do not retry
            raise e
        except Exception as e:
            print(f"Fetch attempt {attempt+1} failed: {e}")
            if attempt == 2:
                raise HTTPException(status_code=500, detail=f"Failed to fetch transcript after 3 attempts: {str(e)}")
            time.sleep(1) # Small delay before retry
    
    try:
        formatted_transcript = []
        full_text = ""
        for entry in transcript_list:
            clean_text = clean_transcript_text(entry.text)
            if not clean_text:
                continue
                
            formatted_transcript.append({
                "text": clean_text,
                "start": entry.start,
                "duration": entry.duration
            })
            full_text += clean_text + " "

        # Backend Sentence Processing
        full_text = full_text.strip()
        # Split by . ! ? while keeping the delimiters, then group into logical lines
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', full_text) if s.strip()]

        return {
            "video_id": video_id,
            "info": video_info,
            "transcript": formatted_transcript,
            "full_text": full_text,
            "sentences": sentences
        }
    except TranscriptsDisabled:
        raise HTTPException(status_code=404, detail="Transcripts are disabled for this video")
    except NoTranscriptFound:
        raise HTTPException(status_code=404, detail="No transcript found for this video")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

@app.get("/channel/videos")
@limiter.limit("10/minute")
async def get_channel_videos(request: Request, url: str = Query(..., description="The YouTube channel or playlist URL")):
    """
    Returns a list of videos in a channel or playlist with automatic retries.
    """
    videos = None
    for attempt in range(3):
        try:
            print(f"Listing attempt {attempt+1} for: {url}")
            videos = extract_channel_videos(url)
            if videos and len(videos) > 0:
                break
            # If empty or None, wait and retry
            await asyncio.sleep(1)
        except Exception as e:
            print(f"Extraction attempt {attempt+1} failed: {e}")
            if attempt < 2:
                await asyncio.sleep(1)

    if not videos:
        raise HTTPException(status_code=404, detail="No videos found or unable to fetch channel/playlist after retries.")
    
    return {"videos": videos}

@app.post("/channel/zip")
@limiter.limit("5/minute")
async def get_channel_zip(
    request: Request,
    background_tasks: BackgroundTasks,
    data: Dict = None,
    format: str = Query("txt", description="The export format (txt, csv, md, json)"),
    include_timestamps: bool = Query(True, description="Whether to include timestamps")
):
    """
    Triggers batch transcription in the background and returns a batch_id.
    """
    if not data or 'videos' not in data:
        raise HTTPException(status_code=400, detail="Missing video list.")

    videos = data['videos']
    if not videos:
        raise HTTPException(status_code=400, detail="Video list is empty.")

    batch_id = f"batch_{int(time.time())}_{random.randint(1000, 9999)}"
    active_batches[batch_id] = {
        "status": "processing",
        "progress": 0,
        "total": len(videos),
        "completed": 0,
        "zip_data": None,
        "format": format,
        "error": None
    }

    background_tasks.add_task(
        process_batch_background, 
        batch_id, 
        videos, 
        format, 
        include_timestamps
    )

    return {"batch_id": batch_id}

async def process_batch_background(batch_id: str, videos: List[Dict], format: str, include_timestamps: bool):
    """Background task to process videos and update global state."""
    job = active_batches[batch_id]
    cookies_path = get_cookies()
    semaphore = asyncio.Semaphore(5)
    
    total = len(videos)
    print(f"\n[Background] Job {batch_id} started: {total} videos")

    async def process_video(video):
        video_id = video['url'].split('=')[-1]
        async with semaphore:
            try:
                await asyncio.sleep(random.uniform(0.1, 0.5))
                transcript_list = None
                for attempt in range(3):
                    try:
                        proxy_config = get_webshare_config()
                        session = requests.Session()
                        if cookies_path:
                            try:
                                cj = http.cookiejar.MozillaCookieJar(cookies_path)
                                cj.load(ignore_discard=True, ignore_expires=True)
                                session.cookies = cj
                            except: pass
                        
                        loop = asyncio.get_event_loop()
                        api = YouTubeTranscriptApi(proxy_config=proxy_config, http_client=session)
                        transcript_list = await loop.run_in_executor(None, api.fetch, video_id)
                        break
                    except Exception as e:
                        if attempt < 2: await asyncio.sleep(1)

                if not transcript_list:
                    return None

                cleaned_segments = []
                for entry in transcript_list:
                    clean_text = clean_transcript_text(entry.text)
                    if clean_text:
                        cleaned_segments.append({
                            "text": clean_text,
                            "start": entry.start,
                            "duration": entry.duration
                        })
                
                if not cleaned_segments:
                    return None

                content = get_formatted_content(
                    video['title'], 
                    video['url'], 
                    cleaned_segments, 
                    format, 
                    include_timestamps
                )
                
                safe_title = "".join([c for c in video['title'] if c.isalnum() or c in (' ', '-', '_')]).strip()
                safe_title = safe_title[:50] or video_id
                
                job["completed"] += 1
                job["progress"] = int((job["completed"] / total) * 100)
                print(f"✅ [{job['completed']}/{total}] {job['progress']}% - {safe_title}")
                
                return {"filename": f"{safe_title}.{format}", "content": content}
            except Exception as e:
                job["completed"] += 1 # Still count as progress even if failed
                job["progress"] = int((job["completed"] / total) * 100)
                print(f"⚠️ Error for {video_id}: {e}")
                return None

    tasks = [process_video(v) for v in videos]
    results = await asyncio.gather(*tasks)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for res in results:
            if res:
                zip_file.writestr(res["filename"], res["content"])

    if len(zip_buffer.getvalue()) < 100:
        job["status"] = "failed"
        job["error"] = "No transcripts could be extracted."
    else:
        job["status"] = "completed"
        job["zip_data"] = zip_buffer.getvalue()
    
    print(f"[Background] Job {batch_id} finished with status: {job['status']}")

@app.get("/batch/status/{batch_id}")
async def get_batch_status(batch_id: str):
    """Polling endpoint for frontend progress."""
    job = active_batches.get(batch_id)
    if not job:
        raise HTTPException(status_code=404, detail="Batch Job not found.")
    
    return {
        "status": job["status"],
        "progress": job["progress"],
        "completed": job["completed"],
        "total": job["total"],
        "error": job["error"]
    }

@app.get("/batch/download/{batch_id}")
async def download_batch_result(batch_id: str):
    """Endpoint to download the finished ZIP archive."""
    job = active_batches.get(batch_id)
    if not job or job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not ready or failed.")
    
    buffer = io.BytesIO(job["zip_data"])
    return StreamingResponse(
        buffer,
        media_type="application/x-zip-compressed",
        headers={"Content-Disposition": f"attachment; filename=transcription_batch_{batch_id}.zip"}
    )

@app.get("/health")
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    # Enable reload for development
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
