import re
import json
import random
import requests
from typing import List, Dict, Optional

# Proxy credentials (Hardcoded for reliability)
WEBSHARE_USER = "znxcztag"
WEBSHARE_PASS = "hi7oonlzr7ea"

# List of common browser User-Agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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

def extract_channel_videos(channel_url: str) -> Optional[List[Dict]]:
    """
    Extracts video titles and URLs from a YouTube channel's /videos page
    using Webshare proxies to bypass blocking.
    """
    if not channel_url.endswith("/videos") and not "/playlist" in channel_url:
        channel_url = channel_url.rstrip("/") + "/videos"

    print(f"Fetching from: {channel_url} using Webshare Proxy...")
    
    try:
        proxies = get_rotating_proxy_dict()
        response = requests.get(channel_url, headers=get_random_headers(), proxies=proxies, timeout=15)
        response.raise_for_status()
        
        # YouTube embeds page data in a JSON object called ytInitialData
        json_pattern = r'var ytInitialData = (\{.*?\});'
        match = re.search(json_pattern, response.text)
        
        if not match:
            print("Could not find video data. YouTube layout might have changed or requested blocked.")
            return None

        data = json.loads(match.group(1))
        videos = []

        # Logic for Channel /videos page
        if "/videos" in channel_url:
            try:
                tabs = data['contents']['twoColumnBrowseResultsRenderer']['tabs']
                video_tab_content = None
                for tab in tabs:
                    if 'richGridRenderer' in tab.get('tabRenderer', {}).get('content', {}):
                        video_tab_content = tab['tabRenderer']['content']['richGridRenderer']
                        break
                
                if video_tab_content:
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
            except Exception as e:
                print(f"Error parsing channel grid: {e}")

        # Logic for Playlist page
        elif "/playlist" in channel_url:
            try:
                # Playlists usually have a different structure
                # contents -> twoColumnBrowseResultsRenderer -> tabs -> [0] -> content -> sectionListRenderer -> contents -> [0] -> itemSectionRenderer -> contents -> [0] -> playlistVideoListRenderer -> contents
                # Alternatively: contents -> twoColumnBrowseResultsRenderer -> playlists -> ... (not usually)
                # Let's try the common one for playlist page:
                sidebar = data.get('sidebar', {})
                # Usually titles are in sidebar, but videos are in contents
                
                playlist_items = []
                # Drill down into the main content
                try:
                    section = data['contents']['twoColumnBrowseResultsRenderer']['tabs'][0]['tabRenderer']['content']['sectionListRenderer']['contents'][0]['itemSectionRenderer']['contents'][0]['playlistVideoListRenderer']
                    playlist_items = section.get('contents', [])
                except:
                    # Fallback for some layouts
                    try:
                        section = data['contents']['twoColumnBrowseResultsRenderer']['playlists'][0]['playlistVideoListRenderer']
                        playlist_items = section.get('contents', [])
                    except:
                        pass

                for item in playlist_items:
                    renderer = item.get('playlistVideoRenderer', {})
                    if renderer:
                        title = renderer.get('title', {}).get('runs', [{}])[0].get('text', 'No Title')
                        video_id = renderer.get('videoId')
                        if video_id:
                            videos.append({
                                "title": title,
                                "url": f"https://www.youtube.com/watch?v={video_id}"
                            })
            except Exception as e:
                print(f"Error parsing playlist: {e}")

        return videos

    except Exception as e:
        print(f"An error occurred during extraction: {e}")
        return None

def main():
    url = input("Enter YouTube Channel or Playlist URL: ")
    videos = extract_channel_videos(url)
    if videos:
        print(f"\nFound {len(videos)} videos:")
        for v in videos:
            print(f"- {v['title']} ({v['url']})")
    else:
        print("Failed to find videos.")

if __name__ == "__main__":
    main()
