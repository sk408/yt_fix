import os
import datetime
from typing import Dict, List, Optional, Tuple
import math

import googleapiclient.discovery
from dotenv import load_dotenv
import pandas as pd
import numpy as np

# Load environment variables
load_dotenv()

class YouTubeAPI:
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the YouTube API client.
        
        Args:
            api_key: YouTube Data API key. If None, will try to load from environment variable.
        """
        if api_key is None:
            api_key = os.getenv("YOUTUBE_API_KEY")
            if not api_key:
                raise ValueError("No API key provided and YOUTUBE_API_KEY not found in environment")
        
        self.youtube = googleapiclient.discovery.build(
            "youtube", "v3", developerKey=api_key
        )
    
    def get_channel_id(self, channel_username: str) -> str:
        """Get channel ID from channel username."""
        request = self.youtube.channels().list(
            part="id",
            forUsername=channel_username
        )
        response = request.execute()
        
        if not response.get("items"):
            # Try as a custom URL
            request = self.youtube.search().list(
                part="snippet",
                q=channel_username,
                type="channel",
                maxResults=1
            )
            response = request.execute()
            
            if not response.get("items"):
                raise ValueError(f"Channel '{channel_username}' not found")
        
        return response["items"][0]["id"]
    
    def get_all_videos(self, channel_id: str) -> List[Dict]:
        """Get all videos from a channel."""
        videos = []
        next_page_token = None
        
        while True:
            request = self.youtube.search().list(
                part="snippet",
                channelId=channel_id,
                maxResults=50,
                order="date",
                type="video",
                pageToken=next_page_token
            )
            response = request.execute()
            
            # Extract video IDs
            video_ids = [item["id"]["videoId"] for item in response["items"]]
            
            # Get video details
            video_details = self._get_video_details(video_ids)
            videos.extend(video_details)
            
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
        
        return videos
    
    def _get_video_details(self, video_ids: List[str]) -> List[Dict]:
        """Get detailed information for a list of video IDs."""
        request = self.youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(video_ids)
        )
        response = request.execute()
        
        videos = []
        for item in response["items"]:
            # Extract relevant information
            video_data = {
                "id": item["id"],
                "title": item["snippet"]["title"],
                "description": item["snippet"]["description"],
                "published_at": item["snippet"]["publishedAt"],
                "thumbnail": item["snippet"]["thumbnails"]["high"]["url"],
                "view_count": int(item["statistics"].get("viewCount", 0)),
                "like_count": int(item["statistics"].get("likeCount", 0)),
                "comment_count": int(item["statistics"].get("commentCount", 0)),
                "duration": item["contentDetails"]["duration"],
                "url": f"https://www.youtube.com/watch?v={item['id']}"
            }
            videos.append(video_data)
        
        return videos
    
    def calculate_video_scores(self, videos: List[Dict], 
                              like_weight: float = 1.0, 
                              view_weight: float = 0.1,
                              half_life_days: int = 90) -> pd.DataFrame:
        """Calculate scores for videos based on likes, views, and recency.
        
        Args:
            videos: List of video data dictionaries
            like_weight: Weight for likes in the score calculation
            view_weight: Weight for views in the score calculation
            half_life_days: Number of days after which a video's score is halved
        
        Returns:
            DataFrame with videos and their scores
        """
        df = pd.DataFrame(videos)
        
        # Convert published_at to datetime
        df["published_at"] = pd.to_datetime(df["published_at"])
        
        # Calculate days since publication
        now = datetime.datetime.now(datetime.timezone.utc)
        df["days_since_published"] = (now - df["published_at"]).dt.total_seconds() / (60 * 60 * 24)
        
        # Calculate time decay factor (half-life formula)
        decay_constant = math.log(2) / half_life_days
        df["time_decay_factor"] = np.exp(-decay_constant * df["days_since_published"])
        
        # Calculate engagement score
        df["engagement_score"] = (df["like_count"] * like_weight + 
                                 df["view_count"] * view_weight)
        
        # Calculate final score
        df["score"] = df["engagement_score"] * df["time_decay_factor"]
        
        # Sort by score in descending order
        df = df.sort_values("score", ascending=False).reset_index(drop=True)
        
        return df 