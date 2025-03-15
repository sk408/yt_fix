import os
import datetime
from typing import Dict, List, Optional, Tuple
import math

import googleapiclient.discovery
from dotenv import load_dotenv
import pandas as pd
import numpy as np
from utils import format_number

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
    
    def get_channel_info(self, channel_username: str, allow_partial_matches: bool = False) -> Dict:
        """Get comprehensive channel information in a single API call.
        
        This method retrieves the channel ID, uploads playlist ID, and video count
        in a single API call when possible.
        
        Args:
            channel_username: Channel username, handle, custom URL, or ID
            allow_partial_matches: If True, allow partial matches when exact match is not found
            
        Returns:
            Dict containing channel_id, uploads_playlist_id, and video_count
            
        Raises:
            ValueError: If the channel cannot be found
        """
        # Check cache first
        if channel_username in self.cache["channel_info"]:
            return self.cache["channel_info"][channel_username]
            
        # Handle URL formats first
        if "youtube.com/" in channel_username or "youtu.be/" in channel_username:
            # Handle YouTube URL formats
            if "youtube.com/c/" in channel_username:
                # Legacy custom URL format
                username = channel_username.split("/c/")[-1].split("/")[0].split("?")[0]
                channel_username = username
            elif "youtube.com/@" in channel_username:
                # Handle format - preserve the @ for forHandle parameter
                username = channel_username.split("@")[-1].split("/")[0].split("?")[0]
                channel_username = username  # Remove the @ since we'll use the forHandle parameter
            elif "youtube.com/channel/" in channel_username:
                # Direct channel ID format - extract and use directly
                channel_id = channel_username.split("/channel/")[-1].split("/")[0].split("?")[0]
                channel_username = channel_id
            elif "youtube.com/user/" in channel_username:
                # Legacy username format
                username = channel_username.split("/user/")[-1].split("/")[0].split("?")[0]
                channel_username = username
                
        # Check if this is a handle (starts with @)
        is_handle = channel_username.startswith('@')
        if is_handle:
            # Remove @ for the API call
            handle_name = channel_username[1:]
        else:
            handle_name = channel_username
                
        # Determine if input is already a channel ID
        is_channel_id = channel_username.startswith('UC') and len(channel_username) >= 20
        
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
        
        # For handles - use forHandle parameter (new in API v3)
        # This should work for both @vegasmatt and vegasmatt formats
        try:
            print(f"Trying to find channel with handle: {handle_name}")
            # Try multiple search terms for better matching
            search_terms = [
                f"@{handle_name}",  # With @ symbol
                handle_name,        # Without @ symbol
                handle_name.replace('_', ' '),  # Replace underscores with spaces
                f"\"{handle_name}\"" # Exact match with quotes
            ]
            
            all_items = []
            
            # Try each search term
            for search_term in search_terms:
                request = self.youtube.search().list(
                    part="snippet",
                    q=search_term,
                    type="channel",
                    maxResults=10
                )
                search_response = self._execute_api_request(request)
                
                if search_response.get("items"):
                    all_items.extend(search_response["items"])
            
            # Remove duplicates by channel ID
            seen_channel_ids = set()
            unique_items = []
            for item in all_items:
                channel_id = item["snippet"]["channelId"]
                if channel_id not in seen_channel_ids:
                    seen_channel_ids.add(channel_id)
                    unique_items.append(item)
            
            # Debug information
            for item in unique_items:
                print(f"Found channel: '{item['snippet']['title']}' (ID: {item['snippet']['channelId']})")
            
            handle_response = {"items": unique_items}
            
            if handle_response.get("items"):
                # First pass: Look for an exact handle match in title or custom URL
                for item in handle_response["items"]:
                    channel_title = item["snippet"]["title"].lower()
                    channel_id = item["snippet"]["channelId"]
                    
                    # Debug information
                    print(f"Found channel: '{item['snippet']['title']}' (ID: {channel_id})")
                    
                    # Check for exact matches in various ways
                    if (f"@{handle_name.lower()}" in channel_title or 
                        handle_name.lower() == channel_title or
                        f"youtube.com/@{handle_name.lower()}" in item["snippet"]["description"].lower()):
                        print(f"Found exact match for handle @{handle_name}!")
                        
                        # Now get the full channel details using the channel ID
                        details_request = self.youtube.channels().list(
                            part="contentDetails,statistics",
                            id=channel_id
                        )
                        details_response = self._execute_api_request(details_request)
                        
                        if details_response.get("items"):
                            print(f"Retrieved details for channel with ID: {channel_id}")
                            channel_info = {
                                "channel_id": channel_id,
                                "uploads_playlist_id": details_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"],
                                "video_count": int(details_response["items"][0]["statistics"]["videoCount"])
                            }
                            self.cache["channel_info"][channel_username] = channel_info
                            return channel_info
                
                # Second pass: For any handle search, try comparing without @ symbol in various combinations
                for item in handle_response["items"]:
                    channel_title = item["snippet"]["title"].lower()
                    channel_id = item["snippet"]["channelId"]
                    handle_no_at = handle_name.lower().replace('@', '')
                    
                    # More flexible matching for well-known channels
                    if (handle_no_at in channel_title.replace(' ', '').lower() or
                        handle_no_at.replace('_', '') in channel_title.replace(' ', '').lower() or
                        channel_title.replace(' ', '').lower() in handle_no_at):
                        
                        print(f"Found match using flexible comparison for handle: {handle_name}")
                        
                        # Get the channel details
                        details_request = self.youtube.channels().list(
                            part="contentDetails,statistics",
                            id=channel_id
                        )
                        details_response = self._execute_api_request(details_request)
                        
                        if details_response.get("items"):
                            print(f"Retrieved details for channel with ID: {channel_id}")
                            channel_info = {
                                "channel_id": channel_id,
                                "uploads_playlist_id": details_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"],
                                "video_count": int(details_response["items"][0]["statistics"]["videoCount"])
                            }
                            self.cache["channel_info"][channel_username] = channel_info
                            return channel_info
            
            print(f"No channel found with handle: {handle_name}")
        except Exception as e:
            print(f"Error looking up channel by handle: {str(e)}")
        
        # Try with forUsername if handle lookup failed
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
            # First try to find an exact match in the results
            exact_match_id = None
            partial_matches = []
            
            for item in response["items"]:
                channel_title = item["snippet"]["title"].lower()
                search_term = channel_username.lower()
                
                if channel_title == search_term:
                    # We found an exact match, use it
                    exact_match_id = item["snippet"]["channelId"]
                    break
                elif search_term in channel_title:
                    # Track partial matches for later use
                    partial_matches.append({
                        "id": item["snippet"]["channelId"],
                        "title": item["snippet"]["title"]
                    })
            
            # If we found an exact match, use it
            if exact_match_id:
                return self.get_channel_info(exact_match_id)
            
            # Changed behavior: Only use partial matches if explicitly allowed
            if partial_matches:
                channel_titles = [f"'{match['title']}'" for match in partial_matches]
                titles_str = ", ".join(channel_titles)
                
                # Print a warning about partial matches
                print(f"Warning: No exact match for '{channel_username}'. Found partial matches: {titles_str}")
                
                if allow_partial_matches:
                    # Only use first partial match if allowed
                    print(f"Using first partial match: {partial_matches[0]['title']}")
                    return self.get_channel_info(partial_matches[0]["id"])
                else:
                    # Just print a warning but don't use partial matches
                    print(f"Please use the exact channel name or ID for more precise results.")
                    
                    # If we have only one partial match and it's a clear match, use it anyway
                    if len(partial_matches) == 1 and (
                        partial_matches[0]['title'].lower().replace(' ', '') == channel_username.lower().replace(' ', '') or
                        channel_username.lower().replace('@', '').replace('_', '') in partial_matches[0]['title'].lower().replace(' ', '')
                    ):
                        print(f"Found single clear partial match: {partial_matches[0]['title']}")
                        return self.get_channel_info(partial_matches[0]["id"])
                    
                    # Raise error instead of automatically using a partial match
                    raise ValueError(f"No exact match found for '{channel_username}'. Try using the full channel URL or ID.")
        
        # If all methods fail, raise an error
        raise ValueError(f"Channel '{channel_username}' not found. Try the full channel ID or URL instead.")
    
    def get_channel_id(self, channel_username: str, allow_partial_matches: bool = False) -> str:
        """Get channel ID from channel username, handle, or custom URL.
        
        This is now a wrapper around get_channel_info to maintain backward compatibility.
        
        Args:
            channel_username: Channel username, handle, custom URL, or ID
            allow_partial_matches: If True, allow partial matches when exact match is not found
            
        Returns:
            The channel ID
        """
        channel_info = self.get_channel_info(channel_username, allow_partial_matches=allow_partial_matches)
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
    
    def get_modified_playlist_id_from_channel(self, channel_input: str, allow_partial_matches: bool = False) -> str:
        """Get a modified playlist ID from a channel name, username, or URL.
        
        This method:
        1. Resolves the channel input to a channel ID
        2. Modifies the channel ID by replacing the second character with 'U'
        3. Returns the modified ID to be used as a playlist ID
        
        Args:
            channel_input: Channel name, username, handle, URL, etc.
            allow_partial_matches: If True, allow partial matches when exact match is not found
            
        Returns:
            Modified channel ID to be used as a playlist ID
        """
        print(f"Getting modified playlist ID from: {channel_input}")
        
        # First get the actual channel ID
        channel_info = self.get_channel_info(channel_input, allow_partial_matches=allow_partial_matches)
        channel_id = channel_info["channel_id"]
        
        print(f"Resolved to channel ID: {channel_id}")
        
        # Check that it's a valid UC ID
        if not channel_id.startswith('UC'):
            raise ValueError(f"Invalid channel ID format: {channel_id}. Must start with 'UC'.")
        
        # Modify the channel ID by replacing the second character with 'U'
        modified_id = channel_id[0] + 'U' + channel_id[2:]
        
        print(f"Modified to playlist ID: {modified_id}")
        return modified_id
    
    def get_videos_with_modified_id(self, channel_id: str, progress_callback=None) -> List[Dict]:
        """Get all videos from a channel using the modified channel ID trick.
        
        This method uses an alternative approach where:
        1. The second character of the channel ID is replaced with 'U'
        2. The modified ID is used directly as a playlist ID
        
        This approach is often more reliable than using the uploads playlist.
        
        Args:
            channel_id: The original channel ID
            progress_callback: Optional callback function to report progress (page_count, video_count)
            
        Returns:
            List of video data dictionaries
        """
        try:
            print(f"Alternative method: Starting with channel ID: {channel_id}")
            
            # Get the modified playlist ID
            modified_id = channel_id[0] + 'U' + channel_id[2:] if channel_id.startswith('UC') else None
            
            # If we couldn't create a modified ID, try to get it through the channel info
            if not modified_id:
                print(f"Channel ID doesn't start with UC, looking up channel info: {channel_id}")
                channel_info = self.get_channel_info(channel_id)
                channel_id = channel_info["channel_id"]
                modified_id = channel_id[0] + 'U' + channel_id[2:]
                
            # Direct URL that can be accessed in a browser
            direct_url = f"https://www.youtube.com/playlist?list={modified_id}"
            print(f"Alternative method URL: {direct_url}")
            print(f"  - Original channel ID: {channel_id}")
            print(f"  - Modified playlist ID: {modified_id}")
            
            # Use playlist method directly
            print("Fetching videos with modified ID using playlist API...")
            videos = self.get_videos_from_playlist(
                modified_id, 
                progress_callback=progress_callback
            )
            print(f"Found {len(videos)} videos using the alternative method!")
            return videos
        except Exception as e:
            print(f"Error fetching videos with modified ID: {str(e)}")
            raise e
    
    def get_all_videos(self, channel_id: str, progress_callback=None) -> List[Dict]:
        """Get all videos from a channel.
        
        This method attempts to retrieve videos first using the regular method 
        (uploads playlist), and if that fails, it tries the modified channel ID trick.
        
        Args:
            channel_id: The channel ID
            progress_callback: Optional callback function to report progress (page_count, video_count)
            
        Returns:
            List of video data dictionaries
        """
        try:
            # First try the regular method with uploads playlist
            try:
                # Get channel info (uploads playlist ID and video count) in one call
                channel_info = self.get_channel_info(channel_id)
                uploads_playlist_id = channel_info["uploads_playlist_id"]
                expected_video_count = channel_info["video_count"]
                
                # Tell the user how many videos we expect to find
                print(f"Channel reports {expected_video_count} videos through API")
                # Update progress through callback if provided
                if progress_callback:
                    try:
                        progress_callback(0, 0)  # Initial call
                    except Exception as e:
                        print(f"Error in progress callback: {str(e)}")
                
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
                
                # Check if we got a reasonable number of videos
                if len(videos) >= expected_video_count * 0.9:  # Allow 10% discrepancy
                    return videos
                else:
                    print(f"Retrieved only {len(videos)} videos with traditional method but channel reports {expected_video_count} videos.")
                    print("Trying alternative method with modified channel ID...")
                    # Falling through to the alternative method
            except Exception as e:
                print(f"Error with traditional method: {str(e)}")
                print("Trying alternative method with modified channel ID...")
            
            # If we get here, try the alternative method
            return self.get_videos_with_modified_id(channel_id, progress_callback=progress_callback)
            
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
    
    def get_videos_from_playlist(self, playlist_id: str, progress_callback = None) -> List[Dict]:
        """Get all videos from a playlist directly.
        
        This method retrieves all videos in a playlist by:
        1. Retrieving all video IDs from the playlist
        2. Getting detailed information for each video
        
        Args:
            playlist_id: The playlist ID
            progress_callback: Optional callback function to report progress (page_count, video_count)
            
        Returns:
            List of video data dictionaries
        """
        # Check cache first
        if playlist_id in self.cache["playlist_info"]:
            return self.cache["playlist_info"][playlist_id]
            
        # Special handling for modified channel IDs
        is_modified_channel_id = playlist_id.startswith('UU') and len(playlist_id) > 20
        if is_modified_channel_id:
            print(f"Detected modified channel ID format: {playlist_id}")
            
            # Check if we have a URL-enabled version
            uploads_playlist_enabled = False
            original_channel_id = "UC" + playlist_id[2:]
        
        try:
            # For modified channel IDs (UU...), we'll skip the playlist verification step
            # as they often won't appear in the playlists API but work in playlistItems
            if not is_modified_channel_id:
                # Verify the playlist exists (skip for modified channel IDs)
                request = self.youtube.playlists().list(
                    part="snippet,contentDetails",
                    id=playlist_id
                )
                response = self._execute_api_request(request)
                print(f"Playlist verification response: {response.get('items', [])}")
                
                if not response.get("items"):
                    # If this is potentially a modified channel ID, try to continue anyway
                    if playlist_id.startswith('U') and len(playlist_id) > 20:
                        print(f"Playlist ID '{playlist_id}' not found in playlists API, but trying playlistItems API directly.")
                    else:
                        raise ValueError(f"Playlist with ID '{playlist_id}' not found")
            
            videos = []
            next_page_token = None
            page_count = 0
            
            # Use a very high page limit - especially for modified channel IDs 
            # which can have thousands of videos
            max_pages = 5000
            
            print(f"Using max_pages={max_pages} for playlist ID: {playlist_id}")
            
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
                
                print(f"Fetching page {page_count} of playlist items...")
                
                # Log the exact request we're making
                playlist_request = self.youtube.playlistItems().list(
                    part="snippet",
                    playlistId=playlist_id,
                    maxResults=50,  # Maximum allowed per request
                    pageToken=next_page_token
                )
                
                try:
                    # Execute and get raw response
                    raw_response = playlist_request.execute()
                    self.api_call_count += 1
                    
                    # Log summary of response for debugging
                    items_count = len(raw_response.get("items", []))
                    has_next = bool(raw_response.get("nextPageToken"))
                    print(f"Page {page_count} response: {items_count} items, next page token: {has_next}")
                    
                    if items_count == 0:
                        print(f"Warning: No items found in playlist response on page {page_count}")
                        if page_count == 1:
                            # On first page, this might indicate an invalid ID or permission issue
                            print(f"Debug - Full response for empty first page: {raw_response}")
                        break
                    
                    # Collect video IDs in this batch
                    batch_video_ids = []
                    for item in raw_response["items"]:
                        try:
                            # Some items might be missing the resourceId field if the video was deleted
                            video_id = item["snippet"]["resourceId"]["videoId"]
                            if video_id not in processed_video_ids:
                                batch_video_ids.append(video_id)
                                processed_video_ids.add(video_id)
                        except KeyError as e:
                            print(f"Warning: Skipping item with missing data: {e}")
                    
                    # Add batch to all video IDs list
                    all_video_ids.extend(batch_video_ids)
                    
                    # Get the next page token
                    next_page_token = raw_response.get("nextPageToken")
                    
                    # Update progress through callback if provided
                    if progress_callback:
                        try:
                            progress_callback(page_count, len(all_video_ids))
                        except Exception as e:
                            print(f"Error in progress callback: {str(e)}")
                    
                    # Log progress for long playlists
                    if page_count % 5 == 0 or len(all_video_ids) % 200 == 0:
                        print(f"Processed {page_count} pages, found {len(all_video_ids)} videos so far...")
                    
                    # Break the loop if there are no more pages
                    if not next_page_token:
                        print(f"Completed playlist fetch at page {page_count} with {len(all_video_ids)} videos")
                        break
                        
                except Exception as e:
                    print(f"Error processing playlist page {page_count}: {str(e)}")
                    # Try to continue with next page if possible
                    if next_page_token:
                        continue
                    else:
                        break
            
            # SPECIAL CASE: For channels like vegasmatt that have many more videos than we found
            # Sometimes we need a special approach when only a few videos were found
            if is_modified_channel_id and len(all_video_ids) < 50 and playlist_id.startswith('UU'):
                print(f"Only found {len(all_video_ids)} videos with modified ID, but this might be a large channel.")
                print("Trying special URL-based approach for uploads playlist...")
                
                # Try to directly use other known formats of playlist URLs
                original_channel_id = "UC" + playlist_id[2:]
                
                # Try with the all uploads format used for some channels
                uploads_playlist_formats = [
                    f"UU{original_channel_id[2:]}",  # Standard modified format
                    f"VLUU{original_channel_id[2:]}",  # VL prefix format
                    f"PL{playlist_id[2:]}",    # PL format
                ]
                
                # Try each of the formats in order
                for format_attempt, format_id in enumerate(uploads_playlist_formats):
                    if format_id == playlist_id:
                        continue  # Skip the one we already tried
                        
                    print(f"Trying URL format {format_attempt+1}: {format_id}")
                    try:
                        url = f"https://www.youtube.com/playlist?list={format_id}"
                        print(f"Testing URL: {url}")
                        
                        # Try to retrieve videos with this format
                        playlist_request = self.youtube.playlistItems().list(
                            part="snippet",
                            playlistId=format_id,
                            maxResults=50
                        )
                        playlist_response = self._execute_api_request(playlist_request)
                        
                        if playlist_response.get("items"):
                            # We found a format that works! Process it
                            new_video_ids = []
                            for item in playlist_response["items"]:
                                try:
                                    video_id = item["snippet"]["resourceId"]["videoId"]
                                    if video_id not in processed_video_ids:
                                        new_video_ids.append(video_id)
                                        processed_video_ids.add(video_id)
                                except KeyError:
                                    pass
                            
                            print(f"Found {len(new_video_ids)} videos with format {format_id}")
                            
                            # If we found a substantial number of videos, use this format to get all of them
                            if len(new_video_ids) > 10:
                                print(f"Format {format_id} works! Using it to get all videos...")
                                
                                # Add these initial videos
                                all_video_ids.extend(new_video_ids)
                                
                                # Then continue with pagination on this format
                                next_token = playlist_response.get("nextPageToken")
                                special_page = 1
                                
                                while next_token and special_page < max_pages:
                                    special_page += 1
                                    try:
                                        # Get next page with this format
                                        next_request = self.youtube.playlistItems().list(
                                            part="snippet",
                                            playlistId=format_id,
                                            maxResults=50,
                                            pageToken=next_token
                                        )
                                        next_response = self._execute_api_request(next_request)
                                        
                                        # Process the videos
                                        batch_ids = []
                                        for item in next_response.get("items", []):
                                            try:
                                                vid = item["snippet"]["resourceId"]["videoId"]
                                                if vid not in processed_video_ids:
                                                    batch_ids.append(vid)
                                                    processed_video_ids.add(vid)
                                            except KeyError:
                                                pass
                                        
                                        # Add to our collection
                                        all_video_ids.extend(batch_ids)
                                        print(f"Found additional {len(batch_ids)} videos (page {special_page}), total: {len(all_video_ids)}")
                                        
                                        # Update progress if needed
                                        if progress_callback:
                                            try:
                                                progress_callback(special_page, len(all_video_ids))
                                            except Exception:
                                                pass
                                        
                                        # Get next token
                                        next_token = next_response.get("nextPageToken")
                                        
                                        if not next_token:
                                            print(f"Completed special format approach with {len(all_video_ids)} total videos")
                                            break
                                    except Exception as special_error:
                                        print(f"Error in special pagination: {special_error}")
                                        break
                                
                                # Break out of the format loop since we found a working one
                                break
                    except Exception as format_error:
                        print(f"Format {format_id} failed: {format_error}")
            
            # If we still have too few videos, try a different approach for modified channel IDs
            if is_modified_channel_id and len(all_video_ids) < 50:
                print("Trying alternative API approach for modified channel ID...")
                try:
                    # Try an alternative approach using search instead
                    original_channel_id = "UC" + playlist_id[2:]
                    print(f"Derived original channel ID: {original_channel_id}")
                    
                    # Use search API to find channel videos
                    search_request = self.youtube.search().list(
                        part="id",
                        channelId=original_channel_id,
                        maxResults=50,
                        type="video",
                        order="date"
                    )
                    search_response = self._execute_api_request(search_request)
                    
                    if search_response.get("items"):
                        for item in search_response["items"]:
                            video_id = item["id"]["videoId"]
                            if video_id not in processed_video_ids:
                                all_video_ids.append(video_id)
                                processed_video_ids.add(video_id)
                        
                        print(f"Found {len(all_video_ids)} videos using search API approach")
                except Exception as search_error:
                    print(f"Search API approach failed: {str(search_error)}")
            
            if len(all_video_ids) > 0:
                print(f"Found {len(all_video_ids)} total video IDs. Now fetching video details...")
                
                # Process all video IDs in larger batches (still respecting the 50 limit per request)
                videos = self._get_video_details(all_video_ids)
                
                print(f"Successfully retrieved details for {len(videos)} videos")
                
                # Only cache if we got a reasonable number of videos
                if len(videos) > 0:
                    self.cache["playlist_info"][playlist_id] = videos
                
                return videos
            else:
                print("ERROR: No videos found in playlist")
                raise ValueError(f"No videos could be retrieved from playlist ID: {playlist_id}")
            
        except Exception as e:
            print(f"Error fetching videos from playlist: {str(e)}")
            raise e  # Re-raise the exception to show the error in the UI
    
    def get_api_call_count(self) -> int:
        """Get the number of API calls made by this instance.
        
        Returns:
            Number of API calls made
        """
        return self.api_call_count
        
    def search_channels(self, query: str, max_results: int = 10) -> List[Dict]:
        """Search for YouTube channels matching the query.
        
        Args:
            query: Search query string
            max_results: Maximum number of results to return (default 10)
            
        Returns:
            List of dictionaries with channel information including:
            - id: Channel ID
            - title: Channel title
            - description: Channel description
            - thumbnail_url: URL of channel thumbnail
            - subscriber_count: Number of subscribers (if available)
            - video_count: Number of videos on the channel
            - estimated_calls: Estimated API calls needed to fetch all videos
        """
        # Perform the search
        request = self.youtube.search().list(
            part="snippet",
            q=query,
            type="channel",
            maxResults=max_results
        )
        search_response = self._execute_api_request(request)
        
        results = []
        if not search_response.get("items"):
            return results
            
        # Get channel IDs for detailed info
        channel_ids = [item["snippet"]["channelId"] for item in search_response["items"]]
        
        # Get detailed channel information
        request = self.youtube.channels().list(
            part="snippet,statistics,contentDetails",
            id=",".join(channel_ids)
        )
        channel_response = self._execute_api_request(request)
        
        # Create a map of channel ID to detailed info
        channel_details = {}
        for item in channel_response.get("items", []):
            channel_id = item["id"]
            stats = item.get("statistics", {})
            
            # Estimate API calls needed based on video count
            video_count = int(stats.get("videoCount", 0))
            # Each video page has 50 items, and we need 1 call for each page
            # Plus 1 initial call for the channel info
            estimated_calls = 1 + math.ceil(video_count / 50)
            # Additional calls for video details (1 call per 50 videos)
            estimated_calls += math.ceil(video_count / 50)
            
            channel_details[channel_id] = {
                "subscriber_count": format_number(int(stats.get("subscriberCount", 0))),
                "video_count": video_count,
                "estimated_calls": estimated_calls,
                "uploads_playlist_id": item["contentDetails"]["relatedPlaylists"]["uploads"]
            }
        
        # Combine search results with detailed info
        for item in search_response["items"]:
            channel_id = item["snippet"]["channelId"]
            details = channel_details.get(channel_id, {})
            
            # Get the best thumbnail
            thumbnails = item["snippet"]["thumbnails"]
            thumbnail_url = thumbnails.get("high", {}).get("url")
            if not thumbnail_url:
                thumbnail_url = thumbnails.get("medium", {}).get("url")
            if not thumbnail_url:
                thumbnail_url = thumbnails.get("default", {}).get("url")
            
            results.append({
                "id": channel_id,
                "title": item["snippet"]["title"],
                "description": item["snippet"]["description"],
                "thumbnail_url": thumbnail_url,
                "subscriber_count": details.get("subscriber_count", "N/A"),
                "video_count": details.get("video_count", 0),
                "estimated_calls": details.get("estimated_calls", 10),
                "uploads_playlist_id": details.get("uploads_playlist_id", "")
            })
            
        return results