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

# Add this standalone function after the imports but before the class
def calculate_video_scores(videos: List[Dict], 
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
        DataFrame with videos and their scores, sorted by score in descending order
    """
    if not videos:
        return pd.DataFrame()
    
    # Convert to DataFrame
    df = pd.DataFrame(videos)
    
    # Convert published_at to datetime
    df["published_at"] = pd.to_datetime(df["published_at"])
    
    # Calculate time decay factor based on half-life
    now = datetime.datetime.now(datetime.timezone.utc)
    df["age_days"] = (now - df["published_at"]).dt.total_seconds() / (24 * 3600)
    half_life_seconds = half_life_days * 24 * 3600
    df["time_decay_factor"] = 0.5 ** (df["age_days"] / half_life_days)
    
    # Calculate popularity score (from likes and views)
    df["like_score"] = df["like_count"] * like_weight
    df["view_score"] = df["view_count"] * view_weight
    df["popularity_score"] = df["like_score"] + df["view_score"]
    
    # Calculate final score
    df["score"] = df["popularity_score"] * df["time_decay_factor"]
    
    # Sort by score in descending order
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    
    return df

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
        
        # Add cache for API responses
        self.cache = {
            "channel_info": {},  # Cache for channel information
            "video_details": {},  # Cache for video details
            "playlist_info": {}   # Cache for playlist information
        }
        
        # Initialize API call counter
        self.api_call_count = 0
    
    def _execute_api_request(self, request):
        """Execute an API request and increment the call counter.
        
        Args:
            request: The request object to execute
            
        Returns:
            The response from the API
        """
        self.api_call_count += 1
        return request.execute()
    
    def estimate_channel_api_calls(self, channel_username: str) -> Dict:
        """Estimate the number of API calls needed for a channel.
        
        This method makes minimal API calls to get the video count,
        then estimates the total calls that would be needed.
        
        Args:
            channel_username: Channel username, handle, custom URL, or ID
            
        Returns:
            Dict with estimated calls and actual video count
        """
        # Check if we already have this channel in cache
        if channel_username in self.cache["channel_info"]:
            channel_info = self.cache["channel_info"][channel_username]
            video_count = channel_info["video_count"]
            
            # If all videos are already in cache, only 1 call is needed (to check for new videos)
            cached_videos_count = len([vid for vid in self.cache["video_details"] 
                                     if vid.startswith(channel_username)])
            
            if cached_videos_count >= video_count * 0.9:  # If 90% of videos are cached
                return {
                    "estimated_calls": 1,
                    "video_count": video_count,
                    "already_cached": True
                }
        
        # Not in cache, get the channel info with minimal calls
        start_call_count = self.api_call_count
        try:
            channel_info = self.get_channel_info(channel_username)
            calls_made = self.api_call_count - start_call_count
            video_count = channel_info["video_count"]
            
            # Estimate remaining calls
            # 1. Calls to get playlist items (50 videos per request)
            playlist_calls = math.ceil(video_count / 50)
            
            # 2. Calls to get video details (50 videos per request)
            detail_calls = math.ceil(video_count / 50)
            
            # Total estimated calls
            total_estimated_calls = calls_made + playlist_calls + detail_calls
            
            return {
                "estimated_calls": total_estimated_calls,
                "video_count": video_count,
                "already_cached": False
            }
            
        except Exception as e:
            # If an error occurs, return the error and calls made
            return {
                "error": str(e),
                "calls_made": self.api_call_count - start_call_count
            }
    
    def estimate_playlist_api_calls(self, playlist_id: str) -> Dict:
        """Estimate the number of API calls needed for a playlist.
        
        This method makes minimal API calls to get the playlist size,
        then estimates the total calls that would be needed.
        
        Args:
            playlist_id: Playlist ID
            
        Returns:
            Dict with estimated calls and playlist size
        """
        # Check if playlist is cached
        if playlist_id in self.cache["playlist_info"]:
            playlist_size = len(self.cache["playlist_info"][playlist_id])
            return {
                "estimated_calls": 1,  # Just to check for updates
                "playlist_size": playlist_size,
                "already_cached": True
            }
        
        # Not in cache, need to make at least one call to verify the playlist
        start_call_count = self.api_call_count
        try:
            # Verify the playlist exists and get a page of items to determine size
            request = self.youtube.playlists().list(
                part="contentDetails",
                id=playlist_id
            )
            response = self._execute_api_request(request)
            
            if not response.get("items"):
                raise ValueError(f"Playlist with ID '{playlist_id}' not found")
            
            # Get the total number of items if available
            playlist_size = int(response["items"][0]["contentDetails"]["itemCount"])
            
            # Sample first page of playlist to confirm accessibility
            request = self.youtube.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=5  # Just get a few items to verify access
            )
            test_response = self._execute_api_request(request)
            
            # Calculate estimated calls
            calls_made = self.api_call_count - start_call_count
            
            # 1. Calls to get all playlist items (50 items per request)
            playlist_calls = math.ceil(playlist_size / 50)
            
            # 2. Calls to get video details (50 videos per request)
            detail_calls = math.ceil(playlist_size / 50)
            
            # Total estimated calls (the calls already made + the remaining calls)
            total_estimated_calls = calls_made + playlist_calls + detail_calls - 1  # Subtract the sample call
            
            return {
                "estimated_calls": total_estimated_calls,
                "playlist_size": playlist_size,
                "already_cached": False
            }
            
        except Exception as e:
            # If an error occurs, return the error and calls made
            return {
                "error": str(e),
                "calls_made": self.api_call_count - start_call_count
            }
    
    def get_channel_info(self, channel_username: str) -> Dict:
        """Get comprehensive channel information in a single API call.
        
        This method retrieves the channel ID, uploads playlist ID, and video count
        in a single API call when possible.
        
        Args:
            channel_username: Channel username, handle, custom URL, or ID
            
        Returns:
            Dict containing channel_id, uploads_playlist_id, and video_count
            
        Raises:
            ValueError: If the channel cannot be found
        """
        # Check cache first
        if channel_username in self.cache["channel_info"]:
            return self.cache["channel_info"][channel_username]
            
        # Determine if input is already a channel ID
        is_channel_id = channel_username.startswith('UC') and len(channel_username) == 24
        
        if is_channel_id:
            channel_id = channel_username
            # Get channel details with a single API call
            request = self.youtube.channels().list(
                part="contentDetails,statistics",
                id=channel_id
            )
            response = self._execute_api_request(request)
            
            if not response.get("items"):
                raise ValueError(f"Channel with ID '{channel_id}' not found")
                
            channel_info = {
                "channel_id": channel_id,
                "uploads_playlist_id": response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"],
                "video_count": int(response["items"][0]["statistics"]["videoCount"])
            }
            self.cache["channel_info"][channel_username] = channel_info
            return channel_info
        
        # First try with forUsername
        request = self.youtube.channels().list(
            part="id,contentDetails,statistics",  # Request all needed parts in one call
            forUsername=channel_username
        )
        response = self._execute_api_request(request)
        
        if response.get("items"):
            channel_info = {
                "channel_id": response["items"][0]["id"],
                "uploads_playlist_id": response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"],
                "video_count": int(response["items"][0]["statistics"]["videoCount"])
            }
            self.cache["channel_info"][channel_username] = channel_info
            return channel_info
        
        # Next, try searching by keyword with the exact channel name
        request = self.youtube.search().list(
            part="snippet",
            q=channel_username,
            type="channel",
            maxResults=5  # Increased from 1 to improve chances of finding the channel
        )
        response = self._execute_api_request(request)
        
        if response.get("items"):
            # Try to find an exact or close match in the results
            found_channel_id = None
            for item in response["items"]:
                channel_title = item["snippet"]["title"].lower()
                search_term = channel_username.lower()
                
                # Check for exact match or if the search term is contained in the title
                if channel_title == search_term or search_term in channel_title:
                    found_channel_id = item["snippet"]["channelId"]
                    break
            
            # If no exact match found, use the first result
            if not found_channel_id and response["items"]:
                found_channel_id = response["items"][0]["snippet"]["channelId"]
            
            if found_channel_id:
                # Now get the additional information with one more API call
                # This is necessary because search doesn't return contentDetails and statistics
                return self.get_channel_info(found_channel_id)
        
        # If all methods fail, raise an error
        raise ValueError(f"Channel '{channel_username}' not found. Try the full channel ID or URL instead.")
    
    def get_channel_id(self, channel_username: str) -> str:
        """Get channel ID from channel username, handle, or custom URL.
        
        This is now a wrapper around get_channel_info to maintain backward compatibility.
        
        Args:
            channel_username: Channel username, handle, custom URL, or ID
            
        Returns:
            The channel ID
        """
        channel_info = self.get_channel_info(channel_username)
        return channel_info["channel_id"]
    
    def get_uploads_playlist_id(self, channel_id: str) -> str:
        """Get the 'uploads' playlist ID for a channel.
        
        This is now a wrapper around get_channel_info to maintain backward compatibility.
        
        Args:
            channel_id: The channel ID
            
        Returns:
            The uploads playlist ID
        """
        channel_info = self.get_channel_info(channel_id)
        return channel_info["uploads_playlist_id"]
    
    def get_channel_video_count(self, channel_id: str) -> int:
        """Get the total number of videos in a channel.
        
        This is now a wrapper around get_channel_info to maintain backward compatibility.
        
        Args:
            channel_id: The channel ID
            
        Returns:
            Total number of videos in the channel
        """
        channel_info = self.get_channel_info(channel_id)
        return channel_info["video_count"]
    
    def get_all_videos(self, channel_id: str) -> List[Dict]:
        """Get all videos from a channel using the uploads playlist.
        
        This method retrieves all videos uploaded to a channel by:
        1. Finding the channel's uploads playlist
        2. Retrieving all videos from that playlist
        3. Getting detailed information for each video
        
        Args:
            channel_id: The channel ID
            
        Returns:
            List of video data dictionaries
        """
        try:
            # Get channel info (uploads playlist ID and video count) in one call
            channel_info = self.get_channel_info(channel_id)
            uploads_playlist_id = channel_info["uploads_playlist_id"]
            expected_video_count = channel_info["video_count"]
            
            videos = []
            next_page_token = None
            page_count = 0
            max_pages = 100  # Safety limit to prevent infinite loops
            
            # Create a set to track processed video IDs and avoid duplicates
            processed_video_ids = set()
            
            # Batch video IDs for fewer API calls
            all_video_ids = []
            
            # Fetch videos from the uploads playlist (this can retrieve ALL videos)
            while True:
                page_count += 1
                if page_count > max_pages:
                    print(f"Warning: Reached maximum page count ({max_pages}). Some videos may be missing.")
                    break
                    
                playlist_request = self.youtube.playlistItems().list(
                    part="snippet",
                    playlistId=uploads_playlist_id,
                    maxResults=50,  # Maximum allowed per request
                    pageToken=next_page_token
                )
                playlist_response = self._execute_api_request(playlist_request)
                
                if not playlist_response.get("items"):
                    print("Warning: No items found in playlist response")
                    break
                
                # Collect video IDs in this batch
                batch_video_ids = []
                for item in playlist_response["items"]:
                    video_id = item["snippet"]["resourceId"]["videoId"]
                    if video_id not in processed_video_ids:
                        batch_video_ids.append(video_id)
                        processed_video_ids.add(video_id)
                
                # Add batch to all video IDs list
                all_video_ids.extend(batch_video_ids)
                
                # Get the next page token
                next_page_token = playlist_response.get("nextPageToken")
                
                # Break the loop if there are no more pages
                if not next_page_token:
                    break
            
            # Process all video IDs in larger batches (still respecting the 50 limit per request)
            videos = self._get_video_details(all_video_ids)
            
            # Verify we got all or most videos (some private/deleted videos might be counted but inaccessible)
            if len(videos) < expected_video_count * 0.9:  # Allow 10% discrepancy for private/deleted videos
                print(f"Warning: Retrieved {len(videos)} videos but channel reports {expected_video_count} videos.")
                print("This discrepancy may be due to private, deleted videos, or API limitations.")
            
            return videos
            
        except Exception as e:
            print(f"Error fetching videos: {str(e)}")
            raise e  # Re-raise the exception to show the error in the UI
    
    def _get_video_details(self, video_ids: List[str]) -> List[Dict]:
        """Get detailed information for a list of video IDs."""
        if not video_ids:
            return []
            
        # Check cache for existing video details
        uncached_video_ids = [vid for vid in video_ids if vid not in self.cache["video_details"]]
        
        # Get details for uncached videos
        new_video_details = []
        if uncached_video_ids:
            # YouTube API can only process up to 50 video IDs at a time
            for i in range(0, len(uncached_video_ids), 50):
                chunk = uncached_video_ids[i:i+50]
                
                request = self.youtube.videos().list(
                    part="snippet,statistics,contentDetails",
                    id=",".join(chunk)
                )
                response = self._execute_api_request(request)
                
                for item in response.get("items", []):
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
                    # Add to cache
                    self.cache["video_details"][item["id"]] = video_data
                    new_video_details.append(video_data)
        
        # Combine cached and newly fetched video details
        all_video_details = [self.cache["video_details"][vid] for vid in video_ids if vid in self.cache["video_details"]]
        
        return all_video_details
    
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
            DataFrame with videos and their scores, sorted by score in descending order
        """
        return calculate_video_scores(
            videos, 
            like_weight=like_weight, 
            view_weight=view_weight, 
            half_life_days=half_life_days
        )
    
    def get_videos_from_playlist(self, playlist_id: str) -> List[Dict]:
        """Get all videos from a playlist directly.
        
        This method retrieves all videos in a playlist by:
        1. Retrieving all video IDs from the playlist
        2. Getting detailed information for each video
        
        Args:
            playlist_id: The playlist ID
            
        Returns:
            List of video data dictionaries
        """
        # Check cache first
        if playlist_id in self.cache["playlist_info"]:
            return self.cache["playlist_info"][playlist_id]
            
        try:
            # Verify the playlist exists
            request = self.youtube.playlists().list(
                part="snippet",
                id=playlist_id
            )
            response = self._execute_api_request(request)
            
            if not response.get("items"):
                raise ValueError(f"Playlist with ID '{playlist_id}' not found")
            
            videos = []
            next_page_token = None
            page_count = 0
            max_pages = 100  # Safety limit to prevent infinite loops
            
            # Create a set to track processed video IDs and avoid duplicates
            processed_video_ids = set()
            
            # Batch video IDs for fewer API calls
            all_video_ids = []
            
            # Fetch videos from the playlist
            while True:
                page_count += 1
                if page_count > max_pages:
                    print(f"Warning: Reached maximum page count ({max_pages}). Some videos may be missing.")
                    break
                    
                playlist_request = self.youtube.playlistItems().list(
                    part="snippet",
                    playlistId=playlist_id,
                    maxResults=50,  # Maximum allowed per request
                    pageToken=next_page_token
                )
                playlist_response = self._execute_api_request(playlist_request)
                
                if not playlist_response.get("items"):
                    print("Warning: No items found in playlist response")
                    break
                
                # Collect video IDs in this batch
                batch_video_ids = []
                for item in playlist_response["items"]:
                    video_id = item["snippet"]["resourceId"]["videoId"]
                    if video_id not in processed_video_ids:
                        batch_video_ids.append(video_id)
                        processed_video_ids.add(video_id)
                
                # Add batch to all video IDs list
                all_video_ids.extend(batch_video_ids)
                
                # Get the next page token
                next_page_token = playlist_response.get("nextPageToken")
                
                # Break the loop if there are no more pages
                if not next_page_token:
                    break
            
            # Process all video IDs in larger batches (still respecting the 50 limit per request)
            videos = self._get_video_details(all_video_ids)
            
            # Cache the results
            self.cache["playlist_info"][playlist_id] = videos
            
            return videos
            
        except Exception as e:
            print(f"Error fetching videos from playlist: {str(e)}")
            raise e  # Re-raise the exception to show the error in the UI
    
    def get_api_call_count(self) -> int:
        """Get the current API call count.
        
        Returns:
            The number of API calls made since the YouTubeAPI instance was created
        """
        return self.api_call_count