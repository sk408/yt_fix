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