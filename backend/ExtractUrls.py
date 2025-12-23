import re
import json
import random
import requests
from typing import List, Dict

# List of common browser User-Agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0"
]

def get_random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
    }

def extract_channel_videos(channel_url: str):
    """
    Extracts video titles and URLs from a YouTube channel's /videos page
    without using external libraries like yt-dlp.
    """
    if not channel_url.endswith("/videos"):
        channel_url = channel_url.rstrip("/") + "/videos"

    print(f"Fetching videos from: {channel_url}...\n")
    
    try:
        response = requests.get(channel_url, headers=get_random_headers(), timeout=15)
        response.raise_for_status()
        
        # YouTube embeds page data in a JSON object called ytInitialData
        json_pattern = r'var ytInitialData = (\{.*?\});'
        match = re.search(json_pattern, response.text)
        
        if not match:
            print("Could not find video data on this page. YouTube might be blocking the request or the layout changed.")
            return

        data = json.loads(match.group(1))
        
        # Navigate the complex YouTube JSON structure to find video items
        # Structure varies slightly, but usually:
        # contents -> twoColumnBrowseResultsRenderer -> tabs -> [videos_tab] -> content -> richGridRenderer -> contents
        
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
                return

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
            return

        # for i, video in enumerate(videos, 1):
        #     print(f"{video['title']} | {video['url']}")
            
        # print(f"\nTotal videos found: {len(videos)}")
        return videos

    except Exception as e:
        print(f"An error occurred: {e}")
        return None

def main():
    channel = input("Enter channel link: ")
    return extract_channel_videos(channel)

if __name__ == "__main__":
    main()
