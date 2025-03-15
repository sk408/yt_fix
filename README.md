# YouTube Smart Sorter

A tool that intelligently ranks YouTube videos from a channel based on both recency and popularity.

## Features

- Fetches all videos from a YouTube channel
- Ranks videos using a custom algorithm that considers:
  - Video age (newer videos get a boost)
  - Like count (more likes = higher ranking)
  - View count (more views = higher ranking)
- Provides a user-friendly interface to explore the results

## Setup

1. Clone this repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file with your YouTube API key:
   ```
   YOUTUBE_API_KEY=your_api_key_here
   ```
4. Run the application:
   ```
   streamlit run app.py
   ```

## Getting a YouTube API Key

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the YouTube Data API v3
4. Create credentials (API Key)
5. Copy the API key to your `.env` file

## How the Ranking Algorithm Works

The ranking algorithm uses a time decay function combined with popularity metrics:

```
score = (likes_count * like_weight + views_count * view_weight) * time_decay_factor
```

Where `time_decay_factor` decreases as the video gets older, giving newer videos with decent engagement a chance to rank higher than older videos with very high engagement. 

## Alternative Fetching Method

This tool supports an alternative method for fetching videos from YouTube channels. The standard YouTube API method often doesn't retrieve all videos correctly. The alternative method works by:

1. Taking the channel ID (e.g., UCbCQBD9gKSEnNtIqmKY1R3Q)
2. Replacing the second character with a capital 'U' (e.g., UUbCQBD9gKSEnNtIqmKY1R3Q)
3. Using this modified ID as a playlist ID: https://www.youtube.com/playlist?list=UUbCQBD9gKSEnNtIqmKY1R3Q

This approach bypasses some of the YouTube API limitations by accessing a special playlist that contains all of a channel's videos. This often retrieves significantly more videos than the standard method.

To use this feature:
- In the app, enable the "Use alternative fetch method" checkbox in the "Advanced Options" section of the sidebar
- The app will then directly use the modified ID as a playlist ID
- Alternatively, you can manually construct the URL and enter it directly in "Playlist" mode

You can also access this playlist directly in your browser by constructing the URL with the modified channel ID. 