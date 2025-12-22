import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

app = FastAPI(title="YouTube Transcript API")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    try:
        response = requests.get(url, timeout=10)
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

@app.get("/transcript")
async def get_transcript(url: str = Query(..., description="The YouTube video URL")):
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

    try:
        ytt_api = YouTubeTranscriptApi()
        transcript_list = ytt_api.fetch(video_id)
        
        formatted_transcript = []
        full_text = ""
        for entry in transcript_list:
            formatted_transcript.append({
                "text": entry.text,
                "start": entry.start,
                "duration": entry.duration
            })
            full_text += entry.text + " "

        return {
            "video_id": video_id,
            "info": video_info,
            "transcript": formatted_transcript,
            "full_text": full_text.strip()
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
