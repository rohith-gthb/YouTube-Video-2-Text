import re
import traceback
import json
import os
import random
import requests
import time
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from ExtractUrls import extract_channel_videos
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from youtube_transcript_api.proxies import WebshareProxyConfig
from dotenv import load_dotenv
from datetime import datetime, timezone
import supabase


load_dotenv()

# ---------------------------
# Network and Proxy utilities
# ---------------------------

def get_random_headers():
    return {
        "User-Agent": random.choice(eval(os.getenv("USER_AGENTS"))),
        "Accept-Language": "en-US,en;q=0.9",
    }

def get_webshare_config():
    """Returns a WebshareProxyConfig object for rotating residential proxies."""
    return WebshareProxyConfig(
        proxy_username=os.getenv("WEBSHARE_USER"),
        proxy_password=os.getenv("WEBSHARE_PASS"),
        filter_ip_locations=["US", "GB", "DE"]
    )

def get_rotating_proxy_dict():
    """Returns a proxy dict for 'requests' using Webshare rotating residential endpoint."""
    user = os.getenv("WEBSHARE_USER")
    password = os.getenv("WEBSHARE_PASS")
    proxy_url = f"http://{user}-rotate:{password}@p.webshare.io:80"
    return {"http": proxy_url, "https": proxy_url}

def make_request(url: str, retry_count: int = 3):
    print(f"[Request] Fetching URL: {url}")
    for attempt in range(retry_count):
        try:
            print(f"  Attempt {attempt + 1}/{retry_count}...")
            response = requests.get(url, headers=get_random_headers(), proxies=get_rotating_proxy_dict())
            response.raise_for_status()
            print(f"  [Success] URL fetched.")
            return response
        except requests.exceptions.RequestException as e:
            print(f"  [Error] Attempt {attempt + 1} failed: {e}")
    print(f"  [Failure] Max retries reached for {url}.")
    return None     


# ---------------------------
# YouTube utilities
# ---------------------------

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

def get_video_info(video_id: str) -> Dict:
    url = f"https://www.youtube.com/watch?v={video_id}"
    response = make_request(url)
    if not response:
        raise Exception(f"Failed to fetch video info for {video_id}")

    soup = BeautifulSoup(response.text, "html.parser")

    views_match = re.search(r'"viewCount":"(\d+)"', response.text)
    view_count = views_match.group(1) if views_match else "0"

    def get_meta_content(**kwargs) -> str:
        tag = soup.find("meta", attrs=kwargs) or soup.find("link", attrs=kwargs)
        return tag.get("content", "Unknown") if tag else "Unknown"

    return {
        "video_id": video_id,
        "title": get_meta_content(property="og:title"),
        "author": get_meta_content(itemprop="name"), 
        "thumbnail": get_meta_content(property="og:image"),
        "description": get_meta_content(property="og:description"),
        "publish_date": get_meta_content(itemprop="datePublished"),
        "views": view_count,  # Updated extraction
        "category": get_meta_content(itemprop="genre"),
        "url": url
    }

def get_transcript(yt_transcript_api: YouTubeTranscriptApi, video_id: str, retry_count: int = 3):
    print(f"[Transcript] Fetching transcript for video: {video_id}")
    # print("Available languages:")
    # print(yt_transcript_api.list(video_id))
    
    top_languages_iso = [
        "en",  # English
        "es",  # Spanish
        "hi",  # Hindi
        "pt",  # Portuguese
        "ru",  # Russian
        "id",  # Indonesian
        "de",  # German
        "fr",  # French
        "ja",  # Japanese
        "ko"   # Korean
    ]

    for attempt in range(retry_count):
        try:
            print(f"  Attempt {attempt + 1}/{retry_count}...")
            transcript = yt_transcript_api.fetch(video_id, languages=top_languages_iso)
            print(f"  [Success] Transcript fetched.")
            return transcript
        except TranscriptsDisabled:
            print(f"  [Error] Transcripts are disabled for video {video_id}")
            return None
        except NoTranscriptFound:
            print(f"  [Error] No transcript found for video {video_id}")
            return None
        except Exception as e:
            print(f"  [Error] Fetching transcript failed: {e}")
    return None     

def format_time(seconds: float) -> str:
    d = int(seconds // 86400)
    h = int((seconds % 86400) // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if d > 0:
        return f"{d}:{h:02d}:{m:02d}:{s:02d}"
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def process_transcript(transcript: list):
    processed_transcript = []
    for entry in transcript:
        processed_transcript.append({
            "text": entry["text"],
            "start": entry["start"],
            "duration": entry["duration"],
            "timestamp": format_time(entry["start"]),
        })
    return processed_transcript

# ------------------------
# Database functions
# ------------------------

def clean_transcript_text(text: str) -> str:
    # Robust cleaning: Remove '>>', '>>>', [Music], (Laughter), etc.
    text = text.replace("&gt;&gt;", "").replace("&gt;", "")
    text = re.sub(r'>>+', '', text) 
    text = re.sub(r'\[.*?\]', '', text) 
    text = re.sub(r'\(.*?\)', '', text) 
    return text.strip()

def create_db_connection():
    print("[DB] Connecting to Supabase...")
    try:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            print("  [Error] Missing database credentials in environment.")
            return None
        conn = supabase.create_client(url, key)
        print("  [Success] Database connected.")
        return conn
    except Exception:
        print(f"[Error] Creating database connection:")
        traceback.print_exc()
        return None

def insert_video_info(conn, video_info: dict):
    print(f"[DB] Inserting video info for: {video_info.get('video_id')}")
    try:
        video_info_obj = {
            "video_id": video_info["video_id"], 
            "title": video_info["title"], 
            "author": video_info["author"], 
            "thumbnail": video_info["thumbnail"], 
            "description": video_info["description"], 
            "publish_date": video_info["publish_date"], 
            "views": video_info["views"], 
            "category": video_info["category"], 
            "url": video_info["url"], 
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        conn.table("video_info").insert(video_info_obj).execute()
        print("  [Success] Video info inserted.")
    except Exception:
        print(f"[Error] Inserting video info:")
        traceback.print_exc()   

def insert_transcript(conn, video_id: str, transcript: list):
    print(f"[DB] Inserting transcript for: {video_id}")
    try:
        formatted_transcript = []
        full_text = ""
        for entry in transcript:
            clean_text = clean_transcript_text(entry.text)
            if not clean_text:
                continue
                
            formatted_transcript.append({
                "text": clean_text,
                "start": entry.start,
                "duration": entry.duration,
                "video_timestamp": format_time(entry.start)
            })

            full_text += clean_text + " "

        # Backend Sentence Processing
        full_text = full_text.strip()
        # Split by . ! ? while keeping the delimiters, then group into logical lines
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', full_text) if s.strip()]

        transcript_obj = {
            "video_id": video_id, 
            "transcript": formatted_transcript,
            "full_text": full_text,
            "sentences": sentences,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # transcript_obj_debug = {
        #     "video_id": video_id, 
        #     "transcript": formatted_transcript[:2],
        #     "full_text": full_text[:20],
        #     "sentences": sentences[:20],
        #     "created_at": datetime.now(timezone.utc).isoformat()
        # }
        # print("[DB] Inserting transcript... ")
        # print(json.dumps(transcript_obj_debug, indent=4))

        conn.table("transcripts").insert(transcript_obj).execute()
        print("  [Success] Transcript inserted.")
    except Exception:
        print(f"[Error] Inserting transcript:")
        traceback.print_exc()   

def check_video_info(conn, video_id: str):
    # print(f"[DB] Checking video info cache for: {video_id}")
    try:
        response = conn.table("video_info").select("*").eq("video_id", video_id).execute()
        if response.data:
            print(f"  [Found] Video info exists in DB.")
            return response.data[0]
        print(f"  [Not Found] No cached video info.")
        return None
    except Exception:
        print(f"[Error] Checking video info:")
        traceback.print_exc()
        return None 

def check_transcript(conn, video_id: str):
    # print(f"[DB] Checking transcript cache for: {video_id}")
    try:
        response = conn.table("transcripts").select("*").eq("video_id", video_id).execute()
        if response.data:
            print(f"  [Found] Transcript exists in DB.")
            return response.data[0]
        print(f"  [Not Found] No cached transcript.")
        return None
    except Exception:
        print(f"[Error] Checking transcript:")
        traceback.print_exc()
        return None
    


# ---------------------------
# Main Data Retrieval Logic
# ---------------------------

def get_video_data(yt_transcript_api: YouTubeTranscriptApi, conn, url: str):
    print(f"\n[Process] Starting data retrieval for: {url}")
    try:
        video_id = extract_video_id(url)
        if not video_id:
            print("  [Error] Could not extract video ID.")
            return None
        
        # Check cache
        video_info = check_video_info(conn, video_id)
        if not video_info:
            print("  [Scrape] Video info not cached. Scraping YouTube...")
            video_info = get_video_info(video_id)
            insert_video_info(conn, video_info)
        else:
            print("  [Cache] Using cached video info.")
            
        transcript_data = check_transcript(conn, video_id)
        if not transcript_data:
            print("  [Scrape] Transcript not cached. Fetching from YouTube...")
            transcript = get_transcript(yt_transcript_api, video_id)
            if transcript:
                insert_transcript(conn, video_id, transcript)
            else:
                transcript = None
        else:
            print("  [Cache] Using cached transcript.")
            transcript = transcript_data.get("transcript")
            
        return {"video_info": video_info, "transcript": transcript}
    except Exception:
        print(f"[Error] Fetching video data:")
        traceback.print_exc()
        return None 


# if __name__ == "__main__":
#     conn = create_db_connection()
#     if conn:
#         url = "https://www.youtube.com/watch?v=ZFoNBxpXen4"
#         url = "https://www.youtube.com/@afaqueahmad7117"
#         list_of_videos = []
#         yt_transcript_api = YouTubeTranscriptApi(proxy_config=get_webshare_config())
#         if '/watch?' in url:
#             print("[Process] Extracting video data...")
#             list_of_videos.append(get_video_data(yt_transcript_api, conn, url))
#         else:
#             if '/channel' in url:
#                 print("[Process] Extracting channel videos...")
#             else:
#                 print("[Process] Extracting playlist videos...")
#             videos = extract_channel_videos(url)
#             print(videos)
#             print("** Found", len(videos), "videos")
#             print(videos)
#             for video in videos:
#                 list_of_videos.append(get_video_data(yt_transcript_api, conn, video.get('url')))
#         print("\n[Result] Video Data Sample:")
        
#         if len(list_of_videos) > 0:
#             video_data = list_of_videos[0]
#             print(f"  Title: {video_data.get('video_info', {}).get('title')}")
#             print(f"  Transcript entries: {len(video_data.get('transcript', [])) if video_data.get('transcript') else 0}")
#         else:
#             print("  Failed to retrieve data.")
#     else:
#         print("[Error] Could not proceed without DB connection.")


import concurrent.futures
from functools import partial

# Wrapper function to handle DB connection safely per thread
def process_video_safe(video_url, yt_api):
    # Create a fresh DB connection for this thread to avoid race conditions
    local_conn = create_db_connection() 
    # try:
    if local_conn:
        return get_video_data(yt_api, local_conn, video_url)
    # finally:
    #     if local_conn:
    #         local_conn.close()
    return None

if __name__ == "__main__":
    # 1. Setup
    url = "https://www.youtube.com/@AnshLambaJSR/videos"
    yt_transcript_api = YouTubeTranscriptApi(proxy_config=get_webshare_config())
    list_of_videos = []
    
    # 2. Get the list of URLs (This part is fast enough to keep synchronous)
    if '/watch?' in url:
        video_urls = [url]
    else:
        print("[Process] Extracting video list...")
        video_objects = extract_channel_videos(url)
        video_urls = [v.get('url') for v in video_objects]
    print(f"** Found {len(video_urls)} videos")

    # 3. Parallel Processing
    # max_workers=5 is a safe start to avoid getting IP-banned by YouTube
    print(f"[Process] Fetching data for {len(video_urls)} videos in parallel...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        # Submit all tasks
        # partial lets us pass the fixed 'yt_transcript_api' argument
        worker_func = partial(process_video_safe, yt_api=yt_transcript_api)
        
        # as_completed yields results as they finish, not in order
        future_to_url = {executor.submit(worker_func, url): url for url in video_urls}
        
        for future in concurrent.futures.as_completed(future_to_url):
            try:
                data = future.result()
                if data:
                    list_of_videos.append(data)
                    print(f"Completed: {data.get('video_info', {}).get('title', 'Unknown')}")
            except Exception as exc:
                print(f"[Error] Video processing generated an exception: {exc}")

    # 4. Results
    print(f"\n[Result] Successfully processed {len(video_urls)} videos.")