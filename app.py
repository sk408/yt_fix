import os
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime

from youtube_api import YouTubeAPI
from utils import parse_duration, format_number, plot_score_components

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
</style>
""", unsafe_allow_html=True)

# Initialize session state
if "api_key" not in st.session_state:
    st.session_state.api_key = os.getenv("YOUTUBE_API_KEY", "")
if "videos_df" not in st.session_state:
    st.session_state.videos_df = None
if "channel_id" not in st.session_state:
    st.session_state.channel_id = ""

# Sidebar
with st.sidebar:
    st.title("YouTube Smart Sorter")
    st.markdown("Find the best videos from a YouTube channel using a smart ranking algorithm.")
    
    # API Key input
    api_key = st.text_input("YouTube API Key", value=st.session_state.api_key, type="password")
    
    # Channel input
    channel_input = st.text_input("YouTube Channel Username or URL")
    
    # Algorithm parameters
    st.subheader("Ranking Parameters")
    like_weight = st.slider("Like Weight", 0.1, 5.0, 1.0, 0.1)
    view_weight = st.slider("View Weight", 0.01, 1.0, 0.1, 0.01)
    half_life_days = st.slider("Half-life (days)", 7, 365, 90, 1)
    
    # Fetch button
    fetch_button = st.button("Fetch Videos")
    
    if fetch_button and channel_input and api_key:
        st.session_state.api_key = api_key
        
        with st.spinner("Fetching videos..."):
            try:
                # Initialize API
                youtube_api = YouTubeAPI(api_key)
                
                # Extract channel ID
                if "youtube.com/" in channel_input:
                    # Extract username from URL
                    if "youtube.com/c/" in channel_input or "youtube.com/@" in channel_input:
                        username = channel_input.split("/")[-1]
                    elif "youtube.com/channel/" in channel_input:
                        st.session_state.channel_id = channel_input.split("/")[-1]
                        username = None
                    else:
                        username = channel_input.split("/")[-1]
                else:
                    username = channel_input
                
                # Get channel ID if not directly provided
                if not st.session_state.channel_id and username:
                    st.session_state.channel_id = youtube_api.get_channel_id(username)
                
                # Get videos
                videos = youtube_api.get_all_videos(st.session_state.channel_id)
                
                # Calculate scores
                st.session_state.videos_df = youtube_api.calculate_video_scores(
                    videos, 
                    like_weight=like_weight,
                    view_weight=view_weight,
                    half_life_days=half_life_days
                )
                
                st.success(f"Found {len(videos)} videos!")
                
            except Exception as e:
                st.error(f"Error: {str(e)}")
    
    # About section
    st.markdown("---")
    st.markdown("### About")
    st.markdown(
        "This app uses a custom algorithm to rank YouTube videos based on "
        "both popularity and recency, helping you find quality content."
    )

# Main content
st.title("🎬 YouTube Smart Sorter")

if st.session_state.videos_df is not None and not st.session_state.videos_df.empty:
    df = st.session_state.videos_df
    
    # Add human-readable duration
    df["duration_str"] = df["duration"].apply(parse_duration)
    
    # Add formatted view and like counts
    df["view_count_str"] = df["view_count"].apply(format_number)
    df["like_count_str"] = df["like_count"].apply(format_number)
    
    # Display stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Videos", len(df))
    with col2:
        st.metric("Total Views", format_number(df["view_count"].sum()))
    with col3:
        st.metric("Total Likes", format_number(df["like_count"].sum()))
    
    # Display score components plot
    st.subheader("Score Components for Top Videos")
    fig = plot_score_components(df)
    st.pyplot(fig)
    
    # Display videos
    st.subheader("Ranked Videos")
    
    # Filtering options
    col1, col2 = st.columns(2)
    with col1:
        min_date = df["published_at"].min().date()
        max_date = df["published_at"].max().date()
        date_range = st.date_input(
            "Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )
    with col2:
        search_term = st.text_input("Search in Title")
    
    # Apply filters
    filtered_df = df.copy()
    
    if len(date_range) == 2:
        start_date, end_date = date_range
        filtered_df = filtered_df[
            (filtered_df["published_at"].dt.date >= start_date) &
            (filtered_df["published_at"].dt.date <= end_date)
        ]
    
    if search_term:
        filtered_df = filtered_df[
            filtered_df["title"].str.lower().str.contains(search_term.lower())
        ]
    
    # Display number of filtered videos
    st.write(f"Showing {len(filtered_df)} videos")
    
    # Display videos in a grid
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
    st.info("Enter a YouTube channel username or URL in the sidebar and click 'Fetch Videos' to get started.")
    
    # Example
    st.markdown("### Example")
    st.markdown(
        "Try entering a popular YouTube channel like 'mkbhd' or 'veritasium' to see how the ranking works."
    )
    
    # How it works
    st.markdown("### How it works")
    st.markdown(
        """
        This app uses a custom algorithm to rank YouTube videos based on both popularity and recency:
        
        1. **Fetch Data**: We retrieve all videos from a channel using the YouTube API
        2. **Calculate Scores**: Each video gets a score based on:
           - Like count (weighted by the Like Weight parameter)
           - View count (weighted by the View Weight parameter)
           - Age of the video (using a time decay function)
        3. **Rank Videos**: Videos are ranked by their final score
        
        The time decay function uses a half-life formula, where a video's score is halved after the specified number of days.
        This gives newer videos with decent engagement a chance to rank higher than older videos with very high engagement.
        """
    ) 