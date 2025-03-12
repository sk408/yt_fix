import re
import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

def parse_duration(duration: str) -> str:
    """Convert ISO 8601 duration format to human-readable format.
    
    Args:
        duration: ISO 8601 duration string (e.g., 'PT1H2M3S')
    
    Returns:
        Human-readable duration string (e.g., '1:02:03')
    """
    # Extract hours, minutes, seconds
    hours_match = re.search(r'(\d+)H', duration)
    minutes_match = re.search(r'(\d+)M', duration)
    seconds_match = re.search(r'(\d+)S', duration)
    
    hours = int(hours_match.group(1)) if hours_match else 0
    minutes = int(minutes_match.group(1)) if minutes_match else 0
    seconds = int(seconds_match.group(1)) if seconds_match else 0
    
    # Format as HH:MM:SS or MM:SS
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"

def format_number(num: int) -> str:
    """Format large numbers with K, M, B suffixes.
    
    Args:
        num: Number to format
    
    Returns:
        Formatted string (e.g., '1.2K', '3.4M')
    """
    if num >= 1_000_000_000:
        return f"{num / 1_000_000_000:.1f}B"
    elif num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num / 1_000:.1f}K"
    else:
        return str(num)

def plot_score_components(df: pd.DataFrame, top_n: int = 20) -> plt.Figure:
    """Create a plot showing the components of the score for top videos.
    
    Args:
        df: DataFrame with video data and scores
        top_n: Number of top videos to include
    
    Returns:
        Matplotlib figure
    """
    # Get top N videos
    top_df = df.head(top_n).copy()
    
    # Create a figure
    fig, ax = plt.subplots(figsize=(12, 8))
    
    # Plot bars
    x = np.arange(len(top_df))
    width = 0.35
    
    # Normalize scores for better visualization
    max_score = top_df["score"].max()
    top_df["normalized_score"] = top_df["score"] / max_score
    
    # Plot components
    ax.bar(x, top_df["normalized_score"], width, label="Final Score")
    ax.bar(x + width, top_df["time_decay_factor"], width, label="Time Decay Factor")
    
    # Add labels and title
    ax.set_xlabel("Videos")
    ax.set_ylabel("Normalized Score")
    ax.set_title("Score Components for Top Videos")
    ax.set_xticks(x + width / 2)
    ax.set_xticklabels([f"Video {i+1}" for i in range(len(top_df))], rotation=45)
    ax.legend()
    
    plt.tight_layout()
    return fig 