import re
import traceback
import json
import os
import random
import requests
import time
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
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

# Proxy credentials (Extracted from file)
WEBSHARE_USER = "znxcztag"
WEBSHARE_PASS = "hi7oonlzr7ea"

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

# Load environment variables
load_dotenv()

# Setup Rate Limiting
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="YouTube Transcript API")
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
            # Robust cleaning: Remove '>>', '>>>', [Music], (Laughter), etc.
            text = entry.text
            # Remove HTML entities if any
            text = text.replace("&gt;&gt;", "").replace("&gt;", "")
            # Remove literal >> and variations
            text = re.sub(r'>>+', '', text) 
            text = re.sub(r'\[.*?\]', '', text) # Remove [Music], [Applause]
            text = re.sub(r'\(.*?\)', '', text) # Remove (Laughter)
            clean_text = text.strip()
            
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

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/channel/videos")
@limiter.limit("5/minute")
async def get_channel_videos(request: Request, url: str = Query(..., description="The YouTube channel URL")):
    """
    Returns a list of videos in a channel.
    """
    videos = extract_channel_videos(url)
    if not videos:
        raise HTTPException(status_code=404, detail="No videos found or unable to fetch channel.")
    
    return {
        "videos": videos,
        "debug": {
            "proxy_status": "Webshare Residential Active"
        }
    }

@app.post("/channel/zip")
@limiter.limit("2/minute")
async def get_channel_zip(
    request: Request,
    data: Dict = None,
    format: str = Query("txt", description="The export format (txt, csv, md, json)"),
    include_timestamps: bool = Query(True, description="Whether to include timestamps")
):
    """
    Fetches transcripts for a specific list of video URLs and returns them as a ZIP file.
    """
    if not data or 'videos' not in data:
        raise HTTPException(status_code=400, detail="Missing video list.")

    videos = data['videos']

    if not videos:
        raise HTTPException(status_code=400, detail="Video list is empty.")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        cookies_path = get_cookies()
        total_videos = len(videos)

        for index, video in enumerate(videos, 1):
            video_id = video['url'].split('=')[-1]
            print(f"Processing video {index}/{total_videos}: {video['title']} ({video_id})")
            
        for index, video in enumerate(videos, 1):
            video_id = video['url'].split('=')[-1]
            print(f"Processing video {index}/{total_videos}: {video['title']} ({video_id})")
            
            try:
                # Add a small delay to avoid IP blocking
                await asyncio.sleep(0.5) 
                
                # Retry loop for batch
                transcript_list = None
                for attempt in range(3):
                    try:
                        # Setup session
                        session = requests.Session()
                        session.headers.update(get_random_headers())
                        
                        if cookies_path:
                            try:
                                cj = http.cookiejar.MozillaCookieJar(cookies_path)
                                cj.load(ignore_discard=True, ignore_expires=True)
                                session.cookies = cj
                            except Exception as e:
                                print(f"Error loading cookies: {e}")
                        
                        proxy_config = get_webshare_config()
                        api = YouTubeTranscriptApi(proxy_config=proxy_config, http_client=session)
                        transcript_list = api.fetch(video_id)
                        break
                    except Exception as e:
                        print(f"Batch fetch attempt {attempt+1} failed for {video_id}: {e}")
                        if attempt < 2:
                            time.sleep(1)
                
                if not transcript_list:
                    print(f"Skipping {video_id} after retries.")
                    continue
                
                formatted_transcript = []
                full_text = ""
                for entry in transcript_list:
                    # Robust cleaning
                    text = entry.text
                    text = text.replace("&gt;&gt;", "").replace("&gt;", "")
                    text = re.sub(r'>>+', '', text) 
                    text = re.sub(r'\[.*?\]', '', text) 
                    text = re.sub(r'\(.*?\)', '', text) 
                    clean_text = text.strip()
                    
                    if not clean_text:
                        continue
                        
                    formatted_transcript.append({
                        "text": clean_text,
                        "start": entry.start,
                        "duration": entry.duration
                    })
                    full_text += clean_text + " "
                
                if not formatted_transcript:
                    continue

                content = get_formatted_content(
                    video['title'], 
                    video['url'], 
                    formatted_transcript, 
                    format, 
                    include_timestamps
                )
                
                safe_title = "".join([c for c in video['title'] if c.isalnum() or c in (' ', '-', '_')]).strip()
                safe_title = safe_title[:50] or video_id
                
                zip_file.writestr(f"{safe_title}.{format}", content)
                print(f"Successfully added: {safe_title}")
            except Exception as e:
                print(f"Failed to process {video_id}: {e}")
                continue

    print("Finished creating ZIP archive.")
    if len(zip_buffer.getvalue()) < 100:
        raise HTTPException(status_code=404, detail="No transcripts could be extracted.")

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/x-zip-compressed",
        headers={"Content-Disposition": f"attachment; filename=selected_transcripts_{format}.zip"}
    )

if __name__ == "__main__":
    import uvicorn
    # Enable reload for development
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
