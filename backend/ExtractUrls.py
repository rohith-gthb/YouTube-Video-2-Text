import re
import json
import random
import requests
from typing import List, Dict

# Proxy credentials (Hardcoded for reliability as requested)
WEBSHARE_USER = "znxcztag"
WEBSHARE_PASS = "hi7oonlzr7ea"

# List of common browser User-Agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

def get_random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/"
    }

def get_rotating_proxy_dict():
    """Returns a proxy dict for 'requests' using Webshare rotating residential endpoint."""
    proxy_url = f"http://{WEBSHARE_USER}-rotate:{WEBSHARE_PASS}@p.webshare.io:80"
    return {"http": proxy_url, "https": proxy_url}

def extract_channel_videos(channel_url: str):
    """
    Extracts video titles and URLs from a YouTube channel's /videos page
    using Webshare proxies to bypass blocking.
    """
    if not channel_url.endswith("/videos"):
        channel_url = channel_url.rstrip("/") + "/videos"

    print(f"Fetching videos from: {channel_url} using Webshare Proxy...")
    
    try:
        proxies = get_rotating_proxy_dict()
        response = requests.get(channel_url, headers=get_random_headers(), proxies=proxies, timeout=15)
        response.raise_for_status()
        
        # YouTube embeds page data in a JSON object called ytInitialData
        json_pattern = r'var ytInitialData = (\{.*?\});'
        match = re.search(json_pattern, response.text)
        
        if not match:
            print("Could not find video data on this page. YouTube might be blocking the request or the layout changed.")
            return None

        data = json.loads(match.group(1))
        
        # Navigate the complex YouTube JSON structure to find video items
        videos = []
        try:
            tabs = data['contents']['twoColumnBrowseResultsRenderer']['tabs']
            # Find the videos tab (usually index 1, but we'll search for it)
            video_tab_content = None
            for tab in tabs:
                if 'richGridRenderer' in tab.get('tabRenderer', {}).get('content', {}):
                    video_tab_content = tab['tabRenderer']['content']['richGridRenderer']
                    break
            
            if not video_tab_content:
                print("Could not find the video grid. This might be a private channel or empty.")
                return []

            items = video_tab_content.get('contents', [])
            for item in items:
                rich_item = item.get('richItemRenderer', {}).get('content', {}).get('videoRenderer', {})
                if rich_item:
                    title = rich_item.get('title', {}).get('runs', [{}])[0].get('text', 'No Title')
                    video_id = rich_item.get('videoId')
                    if video_id:
                        videos.append({
                            "title": title,
                            "url": f"https://www.youtube.com/watch?v={video_id}"
                        })
        except KeyError as e:
            print(f"Error parsing YouTube data structure: {e}")
            return []

        return videos

    except Exception as e:
        print(f"An error occurred during channel extraction: {e}")
        return None
