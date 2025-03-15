import os
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import re
import json
import pathlib
import time
import uuid
import shutil

from youtube_api import YouTubeAPI
from utils import parse_duration, format_number, plot_score_components

# Cache Management Functions
def ensure_cache_dir():
    """Ensure the cache directory exists"""
    cache_dir = pathlib.Path("./cache")
    cache_dir.mkdir(exist_ok=True)
    return cache_dir

def save_to_cache(source_type, source_id, raw_videos, ranking_params, label=None):
    """Save the current results to cache
    
    Args:
        source_type: Type of source (channel or playlist)
        source_id: ID of the source
        raw_videos: List of video data dictionaries
        ranking_params: Dictionary of ranking parameters
        label: Optional label for the cache entry
        
    Returns:
        cache_id: ID of the saved cache entry
    """
    cache_dir = ensure_cache_dir()
    
    # Create a unique ID for this cache entry
    cache_id = str(uuid.uuid4())[:8]
    
    # Create cache entry
    cache_entry = {
        "id": cache_id,
        "timestamp": time.time(),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source_type": source_type,
        "source_id": source_id,
        "label": label,
        "video_count": len(raw_videos),
        "ranking_params": ranking_params,
        "raw_videos": raw_videos
    }
    
    # Save to file
    cache_file = cache_dir / f"{cache_id}.json"
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache_entry, f)
    
    return cache_id

def list_cache_entries():
    """List all available cache entries
    
    Returns:
        List of cache entry metadata (without the raw videos)
    """
    cache_dir = ensure_cache_dir()
    entries = []
    
    for cache_file in cache_dir.glob("*.json"):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                entry = json.load(f)
                # Remove raw videos from metadata to save memory
                entry_meta = {k: v for k, v in entry.items() if k != "raw_videos"}
                entries.append(entry_meta)
        except Exception as e:
            print(f"Error reading cache file {cache_file}: {e}")
    
    # Sort by timestamp, newest first
    entries.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return entries

def load_cache_entry(cache_id):
    """Load a specific cache entry
    
    Args:
        cache_id: ID of the cache entry to load
        
    Returns:
        Cache entry data or None if not found
    """
    cache_dir = ensure_cache_dir()
    cache_file = cache_dir / f"{cache_id}.json"
    
    if not cache_file.exists():
        return None
    
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading cache file {cache_file}: {e}")
        return None

def delete_cache_entry(cache_id):
    """Delete a specific cache entry
    
    Args:
        cache_id: ID of the cache entry to delete
        
    Returns:
        True if successful, False otherwise
    """
    cache_dir = ensure_cache_dir()
    cache_file = cache_dir / f"{cache_id}.json"
    
    if not cache_file.exists():
        return False
    
    try:
        cache_file.unlink()
        return True
    except Exception as e:
        print(f"Error deleting cache file {cache_file}: {e}")
        return False

def clear_all_cache():
    """Delete all cache entries
    
    Returns:
        Number of entries deleted
    """
    cache_dir = ensure_cache_dir()
    count = 0
    
    for cache_file in cache_dir.glob("*.json"):
        try:
            cache_file.unlink()
            count += 1
        except Exception as e:
            print(f"Error deleting cache file {cache_file}: {e}")
    
    return count

# Set page config
st.set_page_config(
    page_title="YouTube Smart Sorter",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Add custom CSS
st.markdown("""
<style>
    .video-card {
        border: 1px solid #ddd;
        border-radius: 10px;
        padding: 10px;
        margin-bottom: 10px;
        background-color: #f9f9f9;
    }
    .video-title {
        font-weight: bold;
        font-size: 16px;
        margin-bottom: 5px;
    }
    .video-stats {
        font-size: 14px;
        color: #555;
    }
    .video-score {
        font-weight: bold;
        color: #1e88e5;
    }
    .or-divider {
        text-align: center;
        margin: 10px 0;
        font-weight: bold;
    }
    .api-counter {
        background-color: #f0f0f0;
        padding: 10px;
        border-radius: 5px;
        margin-top: 10px;
        border-left: 3px solid #1e88e5;
    }
    .warning-message {
        background-color: #fff3cd;
        padding: 10px;
        border-radius: 5px;
        margin: 10px 0;
        border-left: 3px solid #ffc107;
    }
    .filter-section {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 20px;
    }
    .filter-header {
        font-weight: bold;
        margin-bottom: 10px;
    }
    .stExpander {
        border: none !important;
        box-shadow: none !important;
    }
</style>
""", unsafe_allow_html=True)

# Main application window layout
st.title("YouTube Smart Sorter")

# Initialize session state for important variables
if "source_type" not in st.session_state:
    st.session_state.source_type = "channel"
if "api_key" not in st.session_state:
    st.session_state.api_key = os.getenv("YOUTUBE_API_KEY", "")
if "videos_df" not in st.session_state:
    st.session_state.videos_df = None
if "channel_id" not in st.session_state:
    st.session_state.channel_id = ""
if "playlist_id" not in st.session_state:
    st.session_state.playlist_id = ""
if "raw_videos" not in st.session_state:
    st.session_state.raw_videos = []
if "show_confirmation" not in st.session_state:
    st.session_state.show_confirmation = False
if "run_fetch" not in st.session_state:
    st.session_state.run_fetch = False
if "last_channel_input" not in st.session_state:
    st.session_state.last_channel_input = ""
if "last_playlist_input" not in st.session_state:
    st.session_state.last_playlist_input = ""
if "api_call_count" not in st.session_state:
    st.session_state.api_call_count = 0
if "total_api_call_count" not in st.session_state:
    st.session_state.total_api_call_count = 0
if "estimate_info" not in st.session_state:
    st.session_state.estimate_info = None
if "cache_entries" not in st.session_state:
    st.session_state.cache_entries = []
if "selected_cache_id" not in st.session_state:
    st.session_state.selected_cache_id = None
if "cache_loaded" not in st.session_state:
    st.session_state.cache_loaded = False
if "like_weight" not in st.session_state:
    st.session_state.like_weight = 1.0
if "view_weight" not in st.session_state:
    st.session_state.view_weight = 0.1
if "half_life_days" not in st.session_state:
    st.session_state.half_life_days = 90
if "channel_search_results" not in st.session_state:
    st.session_state.channel_search_results = []

# Define callback functions for buttons to ensure proper state management
def estimate_api_calls():
    """Callback function for the Estimate API Calls button"""
    st.session_state.show_confirmation = False
    st.session_state.run_estimation = True
    
def confirm_fetch():
    """Callback function for the Proceed with Fetch button"""
    st.session_state.run_fetch = True

def load_from_cache(cache_id):
    """Callback function for loading data from cache"""
    cache_entry = load_cache_entry(cache_id)
    if cache_entry:
        # Load the data from cache
        st.session_state.raw_videos = cache_entry["raw_videos"]
        
        # Set the ranking parameters
        params = cache_entry["ranking_params"]
        st.session_state.like_weight = params["like_weight"]
        st.session_state.view_weight = params["view_weight"]
        st.session_state.half_life_days = params["half_life_days"]
        
        # Recalculate scores with the original parameters
        from youtube_api import calculate_video_scores
        st.session_state.videos_df = calculate_video_scores(
            st.session_state.raw_videos,
            like_weight=params["like_weight"],
            view_weight=params["view_weight"],
            half_life_days=params["half_life_days"]
        )
        
        # Set source info
        st.session_state.source_type = cache_entry["source_type"]
        if cache_entry["source_type"] == "channel":
            st.session_state.channel_id = cache_entry["source_id"]
            st.session_state.last_channel_input = cache_entry["source_id"]
        else:
            st.session_state.playlist_id = cache_entry["source_id"]
            st.session_state.last_playlist_input = cache_entry["source_id"]
        
        # Set cache loaded flag
        st.session_state.cache_loaded = True
        st.session_state.selected_cache_id = cache_id
        
        # Reset filter settings
        st.session_state.filter_settings = {
            "date_range": None,
            "duration_range": None,
            "views_range": None,
            "likes_range": None,
            "search_term": ""
        }
        
        # No API calls were made
        st.session_state.api_call_count = 0

# Function to recalculate scores without refetching data
def recalculate_scores():
    """Recalculate video scores using current parameter settings"""
    if st.session_state.raw_videos is None:
        return
    
    # Get parameters from session state
    like_weight = st.session_state.get('like_weight', 1.0)
    view_weight = st.session_state.get('view_weight', 0.1)
    half_life_days = st.session_state.get('half_life_days', 90)
    
    # Use the standalone function instead of creating a YouTubeAPI instance
    from youtube_api import calculate_video_scores
    
    # Recalculate scores
    st.session_state.videos_df = calculate_video_scores(
        st.session_state.raw_videos,
        like_weight=like_weight,
        view_weight=view_weight,
        half_life_days=half_life_days
    )

# Helper function to convert duration string to seconds
def duration_to_seconds(duration_str):
    """Convert a duration string like '1:23' or '1:23:45' to seconds"""
    parts = duration_str.split(':')
    if len(parts) == 2:  # MM:SS format
        return int(parts[0]) * 60 + int(parts[1])
    elif len(parts) == 3:  # HH:MM:SS format
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return 0

# Initialize additional state for button callbacks
if "run_estimation" not in st.session_state:
    st.session_state.run_estimation = False
if "run_fetch" not in st.session_state:
    st.session_state.run_fetch = False

# Initialize filter states
if "filter_settings" not in st.session_state:
    st.session_state.filter_settings = {
        "date_range": None,
        "duration_range": None,
        "views_range": None,
        "likes_range": None,
        "search_term": ""
    }

# Sidebar
with st.sidebar:
    st.title("YouTube Smart Sorter")
    st.markdown("Find the best videos from a YouTube channel or playlist using a smart ranking algorithm.")
    
    # Cache browser section
    st.subheader("Saved Results")
    
    # Get cache entries and update session state
    st.session_state.cache_entries = list_cache_entries()
    
    if st.session_state.cache_entries:
        st.write(f"Found {len(st.session_state.cache_entries)} saved searches")
        
        # Display cache entries
        for entry in st.session_state.cache_entries:
            # Create entry title with label if available
            if entry.get('label'):
                entry_title = f"{entry['label']} ({entry['date']})"
            else:
                entry_title = f"{entry['source_type'].capitalize()}: {entry['source_id']} ({entry['date']})"
                
            with st.expander(entry_title):
                st.write(f"Videos: {entry['video_count']}")
                st.write(f"Source: {entry['source_type'].capitalize()} - {entry['source_id']}")
                st.write(f"Parameters: Like weight: {entry['ranking_params']['like_weight']}, " 
                       f"View weight: {entry['ranking_params']['view_weight']}, "
                       f"Half-life: {entry['ranking_params']['half_life_days']} days")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Load", key=f"load_{entry['id']}"):
                        load_from_cache(entry['id'])
                        st.success("Loaded from cache!")
                        st.rerun()
                
                with col2:
                    if st.button("Delete", key=f"delete_{entry['id']}"):
                        if delete_cache_entry(entry['id']):
                            if st.session_state.selected_cache_id == entry['id']:
                                st.session_state.selected_cache_id = None
                            st.success("Deleted!")
                            st.rerun()
        
        # Add button to clear all cache
        if st.button("Clear All Cache"):
            count = clear_all_cache()
            st.session_state.selected_cache_id = None
            st.success(f"Deleted {count} cache entries!")
            st.rerun()
    else:
        st.info("No saved results found. Search for videos and use the 'Save Results' button to store them.")
    
    # API Key input
    st.subheader("API Settings")
    api_key = st.text_input("YouTube API Key", value=st.session_state.api_key, type="password")
    
    # Input selection
    st.subheader("Video Source")
    source_type = st.radio("Select Source Type", ["Channel", "Playlist", "Search Channels"], index=0 if st.session_state.source_type == "channel" else (1 if st.session_state.source_type == "playlist" else 2))
    st.session_state.source_type = source_type.lower().replace(" ", "_")

    if st.session_state.source_type == "channel":
        # Channel input
        channel_input = st.text_input("YouTube Channel Username or URL")
        playlist_input = ""  # Reset playlist input
        search_query = ""    # Reset search query
    elif st.session_state.source_type == "playlist":
        # Playlist input
        playlist_input = st.text_input("YouTube Playlist ID or URL")
        channel_input = ""  # Reset channel input
        search_query = ""   # Reset search query
    else:  # search_channels
        # Channel search input
        search_query = st.text_input("Search for YouTube Channels")
        channel_input = ""  # Reset channel input
        playlist_input = "" # Reset playlist input
        
        # Add search button and logic for channel search
        if search_query and st.button("Search Channels"):
            st.session_state.api_key = api_key
            
            with st.spinner("Searching for channels..."):
                try:
                    # Initialize API
                    youtube_api = YouTubeAPI(api_key)
                    
                    # Special channel search function to find multiple channels
                    search_results = youtube_api.search_channels(search_query, max_results=10)
                    
                    if search_results:
                        st.session_state.channel_search_results = search_results
                        st.success(f"Found {len(search_results)} channels!")
                    else:
                        st.error("No channels found. Try a different search term.")
                        st.session_state.channel_search_results = []
                except Exception as e:
                    st.error(f"Error searching for channels: {str(e)}")
                    st.session_state.channel_search_results = []
        
        # Display search results if available
        if "channel_search_results" in st.session_state and st.session_state.channel_search_results:
            st.subheader("Select a Channel to Rate Videos")
            
            # Create columns for better display
            for i, channel in enumerate(st.session_state.channel_search_results):
                col1, col2 = st.columns([1, 3])
                
                with col1:
                    if "thumbnail_url" in channel and channel["thumbnail_url"]:
                        st.image(channel["thumbnail_url"], width=80)
                    else:
                        st.write("🎬")
                        
                with col2:
                    st.write(f"**{channel['title']}**")
                    st.write(f"Subscribers: {channel.get('subscriber_count', 'N/A')}")
                    st.write(f"Videos: {channel.get('video_count', 'N/A')}")
                    
                    # Add Rate Videos button without nested columns
                    if st.button(f"Rate Videos", key=f"select_channel_{i}"):
                        # Set the selected channel as the current channel
                        st.session_state.source_type = "channel"
                        st.session_state.channel_id = channel["id"]
                        st.session_state.last_channel_input = channel["id"]
                        st.session_state.show_confirmation = True
                        st.session_state.estimate_info = {
                            "type": "channel_alternative",
                            "input": channel["title"],
                            "estimated_calls": channel.get("estimated_calls", 10),
                            "item_count": channel.get("video_count", 0),
                            "already_cached": False
                        }
                        # Use st.rerun() instead of the deprecated st.experimental_rerun()
                        st.rerun()
                    
                    # Add a button to view the channel directly on YouTube
                    channel_url = f"https://www.youtube.com/channel/{channel['id']}"
                    st.markdown(f'<a href="{channel_url}" target="_blank"><button style="background-color:#FF0000;color:white;padding:8px 12px;border:none;border-radius:4px;cursor:pointer;">View on YouTube</button></a>', unsafe_allow_html=True)
                
                st.markdown("---")
    
    # Extract playlist ID from URL if needed
    if playlist_input and "youtube.com/playlist" in playlist_input:
        import urllib.parse as urlparse
        from urllib.parse import parse_qs
        
        parsed_url = urlparse.urlparse(playlist_input)
        playlist_id_from_url = parse_qs(parsed_url.query).get('list', [None])[0]
        if playlist_id_from_url:
            playlist_input = playlist_id_from_url
    
    # Algorithm parameters
    st.subheader("Ranking Parameters")
    like_weight = st.slider("Like Weight", 0.1, 5.0, 1.0, 0.1)
    view_weight = st.slider("View Weight", 0.01, 1.0, 0.1, 0.01)
    half_life_days = st.slider("Half-life (days)", 7, 365, 90, 1)
    
    # Add option for exact matching
    st.subheader("Advanced Options")
    allow_partial_matches = st.checkbox("Allow partial channel name matches", value=False, 
                                       help="When disabled (recommended), only exact channel name matches will be returned. Enable only if you're having trouble finding a channel.")
    
    # Reset confirmation if input changes
    if (st.session_state.source_type == "channel" and 
        channel_input != st.session_state.last_channel_input) or \
       (st.session_state.source_type == "playlist" and 
        playlist_input != st.session_state.last_playlist_input):
        st.session_state.show_confirmation = False
        st.session_state.estimate_info = None
    
    # Buttons with callback functions to ensure proper state management
    st.button("Estimate API Calls", on_click=estimate_api_calls, disabled=not (api_key and (channel_input or playlist_input)))
    
    # Process estimation request
    if st.session_state.run_estimation and api_key and (channel_input or playlist_input):
        # Reset the flag
        st.session_state.run_estimation = False
        st.session_state.api_key = api_key
        
        with st.spinner("Estimating required API calls..."):
            try:
                # Initialize API
                youtube_api = YouTubeAPI(api_key)
                
                # Handle channel input
                if st.session_state.source_type == "channel" and channel_input:
                    try:
                        # First get the channel ID, then convert to modified playlist ID
                        modified_id = youtube_api.get_modified_playlist_id_from_channel(channel_input, allow_partial_matches=allow_partial_matches)
                        # Estimate using the playlist estimation method
                        estimate_info = youtube_api.estimate_playlist_api_calls(modified_id)
                        
                        if "error" not in estimate_info:
                            st.session_state.estimate_info = {
                                "type": "channel_alternative",
                                "input": channel_input,
                                "estimated_calls": estimate_info["estimated_calls"],
                                "item_count": estimate_info["playlist_size"],
                                "already_cached": estimate_info.get("already_cached", False)
                            }
                        else:
                            st.error(f"Error estimating API calls: {estimate_info['error']}")
                            st.session_state.estimate_info = None
                    except Exception as e:
                        st.error(f"Error estimating API calls: {str(e)}")
                        st.session_state.estimate_info = None
                
                # Handle playlist input
                elif st.session_state.source_type == "playlist" and playlist_input:
                    estimate_info = youtube_api.estimate_playlist_api_calls(playlist_input)
                    
                    if "error" not in estimate_info:
                        st.session_state.estimate_info = {
                            "type": "playlist",
                            "input": playlist_input,
                            "estimated_calls": estimate_info["estimated_calls"],
                            "item_count": estimate_info["playlist_size"],
                            "already_cached": estimate_info.get("already_cached", False)
                        }
                    else:
                        st.error(f"Error estimating API calls: {estimate_info['error']}")
                        st.session_state.estimate_info = None
                
                else:
                    st.error("Please enter either a channel or playlist identifier.")
                
                # Set the flag to show confirmation
                if st.session_state.estimate_info:
                    st.session_state.show_confirmation = True
                
            except Exception as e:
                st.error(f"Error: {str(e)}")
                st.session_state.estimate_info = None
    
    # Show estimate results and confirmation
    if st.session_state.show_confirmation and st.session_state.estimate_info:
        estimate = st.session_state.estimate_info
        
        # Display estimate info
        if estimate["already_cached"]:
            st.success(f"This content is cached! Only about {estimate['estimated_calls']} API call(s) needed.")
        elif estimate["estimated_calls"] <= 10:
            st.info(f"Estimated API calls: {estimate['estimated_calls']} (Low impact)")
        elif estimate["estimated_calls"] <= 50:
            st.warning(f"Estimated API calls: {estimate['estimated_calls']} (Medium impact)")
        else:
            st.markdown(f"""
            <div class="warning-message">
                <strong>Warning: High API Usage</strong><br>
                This will require approximately {estimate['estimated_calls']} API calls.
                This could use up a significant portion of your daily quota!
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown(f"Content size: {estimate['item_count']} {'videos' if estimate['type'] == 'channel' else 'playlist items'}")
        
        # Show confirmation button
        st.button("Proceed with Fetch", on_click=confirm_fetch)
    
    # Fetch button logic - now uses callback system for reliable execution
    if st.session_state.run_fetch and api_key and (channel_input or playlist_input):
        # Reset the flag so it doesn't run again
        st.session_state.run_fetch = False
        
        # Reset API call counter for this run
        st.session_state.api_call_count = 0
        
        with st.spinner("Fetching videos..."):
            try:
                # Initialize API
                youtube_api = YouTubeAPI(api_key)
                
                # Handle channel input
                if st.session_state.source_type == "channel" and channel_input:
                    # Reset channel_id if the channel input has changed
                    if channel_input != st.session_state.last_channel_input:
                        st.session_state.channel_id = ""
                        st.session_state.last_channel_input = channel_input
                
                    # Get videos from channel using the alternative method
                    # Get the channel ID
                    st.text("Resolving channel identifier...")
                    try:
                        # First try without partial matches
                        channel_info = youtube_api.get_channel_info(channel_input, allow_partial_matches=allow_partial_matches)
                    except ValueError as e:
                        if not allow_partial_matches:
                            # If it fails and partial matches aren't allowed, try again with partial matches
                            # This helps with well-known channels that don't match exactly
                            st.warning("Exact match not found. Trying with partial matching enabled.")
                            channel_info = youtube_api.get_channel_info(channel_input, allow_partial_matches=True)
                        else:
                            # If partial matches are already allowed and we still failed, re-raise
                            raise e
                            
                    channel_id = channel_info["channel_id"]
                    st.session_state.channel_id = channel_id
                    
                    # Console log the channel ID
                    print(f"Channel ID found: {channel_id}")
                    
                    # Modify the channel ID by replacing the second character with 'U'
                    if len(channel_id) < 2:
                        st.error("Invalid channel ID format")
                        st.stop()
                        
                    # Create the modified ID - this is what works in playlist mode
                    modified_id = channel_id[0] + 'U' + channel_id[2:]
                    
                    # Console log the modified ID
                    print(f"Modified channel ID (for playlist): {modified_id}")
                    
                    # Print details for transparency in the UI
                    st.code(f"Channel ID: {channel_id}\nModified ID: {modified_id}", language="python")
                    
                    # Set up the state for playlist mode with the modified ID
                    st.session_state.source_type = "playlist"
                    st.session_state.playlist_id = modified_id
                    st.session_state.last_playlist_input = modified_id
                    
                    # Create the direct URL for reference
                    direct_url = f"https://www.youtube.com/playlist?list={modified_id}"
                    st.info(f"Using modified channel ID as playlist: [Open in YouTube]({direct_url})")
                
                # Handle playlist input
                elif st.session_state.source_type == "playlist" and playlist_input:
                    # Reset playlist_id if the playlist input has changed
                    if playlist_input != st.session_state.last_playlist_input:
                        st.session_state.playlist_id = playlist_input
                        st.session_state.last_playlist_input = playlist_input
                    
                    # Get videos from playlist directly
                    try:
                        # Create a progress bar for visual feedback
                        progress_bar = st.progress(0)
                        progress_placeholder = st.empty()
                        
                        # Function to update progress info in UI
                        def progress_callback(page_count, video_count):
                            # Update progress information in the UI
                            progress_placeholder.write(f"Progress: Retrieved {video_count} videos (page {page_count})")
                            # Since we don't know total, use a moving progress bar
                            progress_value = min(0.1 + (page_count % 10) / 10, 0.95)
                            progress_bar.progress(progress_value)
                        
                        # Get videos from playlist with progress updates
                        videos = youtube_api.get_videos_from_playlist(
                            st.session_state.playlist_id,
                            progress_callback=progress_callback
                        )
                        
                        # Complete the progress bar
                        progress_bar.progress(1.0)
                        
                        print(f"Successfully retrieved {len(videos)} videos from playlist")
                        st.success(f"Found {len(videos)} videos in playlist")
                    except Exception as e:
                        st.error(f"Error retrieving playlist: {str(e)}")
                        st.stop()
                
                else:
                    st.error("Please enter either a channel or playlist identifier.")
                    st.stop()
                
                # Store raw videos in session state
                st.session_state.raw_videos = videos
                
                # Store initial ranking parameters
                st.session_state.like_weight = like_weight
                st.session_state.view_weight = view_weight
                st.session_state.half_life_days = half_life_days
                
                # Calculate scores
                st.session_state.videos_df = youtube_api.calculate_video_scores(
                    videos, 
                    like_weight=like_weight,
                    view_weight=view_weight,
                    half_life_days=half_life_days
                )
                
                # Update API call counter
                st.session_state.api_call_count = youtube_api.get_api_call_count()
                st.session_state.total_api_call_count += st.session_state.api_call_count
                
                # Reset the confirmation dialog
                st.session_state.show_confirmation = False
                st.session_state.estimate_info = None
                
                # Reset filter settings when new data is fetched
                st.session_state.filter_settings = {
                    "date_range": None,
                    "duration_range": None,
                    "views_range": None,
                    "likes_range": None,
                    "search_term": ""
                }
                
                st.success(f"Found {len(videos)} videos!")
                
            except Exception as e:
                st.error(f"Error: {str(e)}")
    
    # Display API call counter
    if st.session_state.api_call_count > 0:
        st.markdown(f"""
        <div class="api-counter">
            <strong>API Calls:</strong> {st.session_state.api_call_count} (last run)<br>
            <strong>Total API Calls:</strong> {st.session_state.total_api_call_count} (all runs)
        </div>
        """, unsafe_allow_html=True)
    
    # About section
    st.markdown("---")
    st.markdown("### About")
    st.markdown(
        "This app uses a custom algorithm to rank YouTube videos based on "
        "both popularity and recency, helping you find quality content."
    )

# Main content
st.title("🎬 YouTube Smart Sorter")

# Show cache status if data is loaded from cache
if st.session_state.cache_loaded and st.session_state.selected_cache_id:
    st.success(f"⚡ Viewing cached results - no API calls were used to load this data")

# Also display API call counter in main interface when videos are displayed
if st.session_state.videos_df is not None and not st.session_state.videos_df.empty:
    df = st.session_state.videos_df.copy()
    
    # Add human-readable duration
    df["duration_str"] = df["duration"].apply(parse_duration)
    
    # Add formatted view and like counts
    df["view_count_str"] = df["view_count"].apply(format_number)
    df["like_count_str"] = df["like_count"].apply(format_number)
    
    # Add duration in seconds for easier filtering
    df["duration_seconds"] = df["duration_str"].apply(duration_to_seconds)
    
    # Display stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Videos", len(df))
    with col2:
        st.metric("Total Views", format_number(df["view_count"].sum()))
    with col3:
        st.metric("Total Likes", format_number(df["like_count"].sum()))
    with col4:
        st.metric("API Calls", st.session_state.api_call_count)
    
    # Add a button to save current results to cache
    cache_cols = st.columns([3, 1])
    
    with cache_cols[0]:
        cache_label = st.text_input("Custom Label (optional)", 
                                  placeholder="E.g., 'Tech videos from MKBHD'")
    
    with cache_cols[1]:
        if st.button("💾 Save Results to Local Cache"):
            # Determine source type and ID
            source_type = st.session_state.source_type
            source_id = (st.session_state.channel_id if source_type == "channel" 
                       else st.session_state.playlist_id)
            
            # Prepare ranking parameters
            ranking_params = {
                "like_weight": float(st.session_state.get('like_weight', 1.0)),
                "view_weight": float(st.session_state.get('view_weight', 0.1)),
                "half_life_days": int(st.session_state.get('half_life_days', 90))
            }
            
            # Save to cache
            if st.session_state.raw_videos:
                cache_id = save_to_cache(source_type, source_id, 
                                       st.session_state.raw_videos, ranking_params, cache_label)
                st.success(f"Results saved to cache! (ID: {cache_id})")
                
                # Update selected cache ID
                st.session_state.selected_cache_id = cache_id
                st.session_state.cache_loaded = True
    
    # Add ranking parameter controls to allow adjusting without refetching
    st.subheader("Adjust Ranking Parameters")
    with st.form(key="ranking_form"):
        ranking_cols = st.columns(3)
        
        with ranking_cols[0]:
            like_weight = st.slider(
                "Like Weight", 
                0.1, 5.0, 
                float(st.session_state.get('like_weight', 1.0)), 
                0.1,
                key="like_weight"
            )
            
        with ranking_cols[1]:
            view_weight = st.slider(
                "View Weight", 
                0.01, 1.0, 
                float(st.session_state.get('view_weight', 0.1)), 
                0.01,
                key="view_weight"
            )
            
        with ranking_cols[2]:
            half_life_days = st.slider(
                "Half-life (days)", 
                7, 365, 
                int(st.session_state.get('half_life_days', 90)), 
                1,
                key="half_life_days"
            )
        
        submit_button = st.form_submit_button(label="Recalculate Scores", on_click=recalculate_scores)
    
    # Display score components plot
    st.subheader("Score Components for Top Videos")
    fig = plot_score_components(df)
    st.pyplot(fig)
    
    # Display videos with enhanced filtering
    st.subheader("Ranked Videos")
    
    # Filtering options
    with st.expander("📊 Filter Videos", expanded=True):
        st.markdown('<div class="filter-section">', unsafe_allow_html=True)
        st.markdown('<div class="filter-header">Filter Options</div>', unsafe_allow_html=True)
        
        # Create multi-column layout for filters
        filter_cols = st.columns(2)
        
        with filter_cols[0]:
            # Date range filter
            min_date = df["published_at"].min().date()
            max_date = df["published_at"].max().date()
            
            date_range = st.date_input(
                "Date Range",
                value=st.session_state.filter_settings["date_range"] or (min_date, max_date),
                min_value=min_date,
                max_value=max_date
            )
            st.session_state.filter_settings["date_range"] = date_range
            
            # Duration filter
            min_duration = int(df["duration_seconds"].min())
            max_duration = int(df["duration_seconds"].max())
            
            # Format duration for display - for information only, not used in slider
            def format_duration_display(seconds):
                minutes, seconds = divmod(seconds, 60)
                hours, minutes = divmod(minutes, 60)
                if hours > 0:
                    return f"{hours}h {minutes}m {seconds}s"
                else:
                    return f"{minutes}m {seconds}s"
            
            # Show duration range information above the slider
            st.write(f"Duration range: {format_duration_display(min_duration)} to {format_duration_display(max_duration)}")
            
            # Use a standard slider with seconds as values
            duration_range = st.slider(
                "Duration (in seconds)",
                min_value=min_duration,
                max_value=max_duration,
                value=st.session_state.filter_settings["duration_range"] or (min_duration, max_duration)
            )
            st.session_state.filter_settings["duration_range"] = duration_range
            
            # Display the selected duration range in a readable format
            min_dur, max_dur = duration_range
            st.write(f"Selected: {format_duration_display(min_dur)} to {format_duration_display(max_dur)}")
        
        with filter_cols[1]:
            # Views filter
            min_views = int(df["view_count"].min())
            max_views = int(df["view_count"].max())
            
            views_range = st.slider(
                "Views",
                min_value=min_views,
                max_value=max_views,
                value=st.session_state.filter_settings["views_range"] or (min_views, max_views),
                format="%d"
            )
            st.session_state.filter_settings["views_range"] = views_range
            
            # Display the selected views range in a formatted way
            min_views_selected, max_views_selected = views_range
            st.write(f"Selected: {format_number(min_views_selected)} to {format_number(max_views_selected)}")
            
            # Likes filter
            min_likes = int(df["like_count"].min())
            max_likes = int(df["like_count"].max())
            
            likes_range = st.slider(
                "Likes",
                min_value=min_likes,
                max_value=max_likes,
                value=st.session_state.filter_settings["likes_range"] or (min_likes, max_likes),
                format="%d"
            )
            st.session_state.filter_settings["likes_range"] = likes_range
            
            # Display the selected likes range in a formatted way
            min_likes_selected, max_likes_selected = likes_range
            st.write(f"Selected: {format_number(min_likes_selected)} to {format_number(max_likes_selected)}")
        
        # Title search (full width)
        search_term = st.text_input(
            "Search in Title",
            value=st.session_state.filter_settings["search_term"]
        )
        st.session_state.filter_settings["search_term"] = search_term
        
        # Reset filters button
        if st.button("Reset All Filters"):
            st.session_state.filter_settings = {
                "date_range": (min_date, max_date),
                "duration_range": (min_duration, max_duration),
                "views_range": (min_views, max_views),
                "likes_range": (min_likes, max_likes),
                "search_term": ""
            }
            # Force refresh
            st.rerun()
            
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Apply filters
    filtered_df = df.copy()
    
    # Date filter
    if len(date_range) == 2:
        start_date, end_date = date_range
        filtered_df = filtered_df[
            (filtered_df["published_at"].dt.date >= start_date) &
            (filtered_df["published_at"].dt.date <= end_date)
        ]
    
    # Duration filter
    if duration_range:
        min_duration, max_duration = duration_range
        filtered_df = filtered_df[
            (filtered_df["duration_seconds"] >= min_duration) &
            (filtered_df["duration_seconds"] <= max_duration)
        ]
    
    # Views filter
    if views_range:
        min_views, max_views = views_range
        filtered_df = filtered_df[
            (filtered_df["view_count"] >= min_views) &
            (filtered_df["view_count"] <= max_views)
        ]
    
    # Likes filter
    if likes_range:
        min_likes, max_likes = likes_range
        filtered_df = filtered_df[
            (filtered_df["like_count"] >= min_likes) &
            (filtered_df["like_count"] <= max_likes)
        ]
    
    # Title search
    if search_term:
        filtered_df = filtered_df[
            filtered_df["title"].str.lower().str.contains(search_term.lower())
        ]
    
    # Display number of filtered videos and percentage
    filtered_percent = (len(filtered_df) / len(df) * 100) if len(df) > 0 else 0
    st.write(f"Showing {len(filtered_df)} of {len(df)} videos ({filtered_percent:.1f}%)")
    
    # Display videos in a grid
    if not filtered_df.empty:
        cols = st.columns(3)
        for i, (_, video) in enumerate(filtered_df.iterrows()):
            col = cols[i % 3]
            with col:
                st.markdown(f"""
                <div class="video-card">
                    <a href="{video['url']}" target="_blank">
                        <img src="{video['thumbnail']}" width="100%">
                    </a>
                    <div class="video-title">{video['title']}</div>
                    <div class="video-stats">
                        👁️ {video['view_count_str']} views &nbsp;|&nbsp; 
                        👍 {video['like_count_str']} likes &nbsp;|&nbsp; 
                        ⏱️ {video['duration_str']}
                    </div>
                    <div class="video-stats">
                        📅 {video['published_at'].strftime('%Y-%m-%d')} &nbsp;|&nbsp; 
                        <span class="video-score">Score: {video['score']:.2f}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.warning("No videos match your filter criteria. Try adjusting your filters.")
else:
    if st.session_state.source_type == "channel":
        st.info("Enter a YouTube channel username or URL in the sidebar, click 'Estimate API Calls', and then 'Proceed with Fetch' to get started.")
    else:
        st.info("Enter a YouTube playlist ID or URL in the sidebar, click 'Estimate API Calls', and then 'Proceed with Fetch' to get started.")
    
    # Examples
    st.markdown("### Examples")
    
    if st.session_state.source_type == "channel":
        st.markdown(
            "Try entering a popular YouTube channel like 'mkbhd' or 'veritasium' to see how the ranking works."
        )
    else:
        st.markdown(
            "Try entering a YouTube playlist ID (like 'PL96C35uN7xGLLeET0dOWaKHkAlPsrkcha') or "
            "a full playlist URL (like 'https://www.youtube.com/playlist?list=PL96C35uN7xGLLeET0dOWaKHkAlPsrkcha')."
        )
    
    # How it works
    st.markdown("### How it works")
    st.markdown(
        """
        This app uses a custom algorithm to rank YouTube videos based on both popularity and recency:
        
        1. **Fetch Data**: We retrieve all videos from a channel or playlist using the YouTube API
        2. **Calculate Scores**: Each video gets a score based on:
           - Like count (weighted by the Like Weight parameter)
           - View weight (weighted by the View Weight parameter) 
           - Recency (newer videos score higher based on the Half-life parameter)
        3. **Rank & Display**: Videos are ranked by their overall score
        
        ### API Usage
        The app now includes an API call estimator to help you manage your quota:
        1. Click "Estimate API Calls" to check how many calls will be needed
        2. Review the estimate and confirm if you want to proceed
        3. For large channels (6000+ videos), this could use over 200 API calls
        """
    ) 