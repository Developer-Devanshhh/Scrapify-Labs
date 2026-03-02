# Scrapify Labs: Credentials & Testing Guide

This guide explains how to get the necessary credentials for each scraping platform and how to test that everything is working.

## 1. Getting Credentials

To scrape live data, you need to configure your `.env` file with credentials for the platforms you want to use.

### Reddit (PRAW)
Reddit offers a free API tier that is perfect for scraping public subreddits.
1. Go to [Reddit Apps](https://www.reddit.com/prefs/apps).
2. Click **Create Another App...** at the bottom.
3. Choose **"script"**.
4. Name: `ScrapifyLabs` (or any name).
5. redirect uri: `http://localhost:8000` (doesn't matter for script).
6. Click **Create app**.
7. Your `REDDIT_CLIENT_ID` is the string under "personal use script".
8. Your `REDDIT_CLIENT_SECRET` is the "secret".
**In `.env`:**
```ini
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=ScrapifyLabs/1.0
```

### YouTube (Data API v3)
YouTube provides a generous 10,000 quota free tier per day.
1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new Project (e.g., "Scrapify Labs").
3. Go to **APIs & Services** -> **Library**.
4. Search for "YouTube Data API v3" and click **Enable**.
5. Go to **Credentials**, click **Create Credentials** -> **API Key**.
6. Copy the generated key.
**In `.env`:**
```ini
YOUTUBE_API_KEY=your_api_key
```

### Twitter / X (twscrape)
Twitter scraping via `twscrape` uses a pool of dummy accounts to fetch data without the official expensive API.
**Note:** It is highly recommended to create **dummy/alt accounts** for this, not your personal account.
1. Create 1 or more dummy Twitter accounts.
2. Formulate the line as: `username:password:email:email_password`
**In `.env`:**
```ini
TWITTER_ACCOUNTS=username1:pass1:email1:emailpass1
# You can add multiple accounts by separating them with a newline if setting as an environment variable, but in the .env file, you might need to handle multiline carefully or just start with 1 account.
```
*(If you leave this empty, Twitter scraping will just be skipped).*

### Instagram (instaloader)
Instagram public scraping (hashtags) often works *without* login. However, logging in prevents rate limiting.
**Note:** Use a **dummy account**, as Instagram can temporarily block heavily scraping accounts.
**In `.env`:**
```ini
# Optional - leave blank to attempt public unauthenticated scraping
INSTAGRAM_USERNAME=dummy_username
INSTAGRAM_PASSWORD=dummy_password
```

### Civic/Government Sites
No credentials needed! This scrapes public portals directly via URL HTTP requests.

---

## 2. How to Test the Services

Once you've filled out your `.env` file, you can test the scraping flows.

### Step A: Start the Server
Make sure you are in your project directory and your virtual environment is activated:
```bash
cd /home/devanshverma/Downloads/Scrapify
source .venv/bin/activate
uvicorn src.main:app --port 8000
```
*The server will start running on http://localhost:8000.*

### Step B: Check Configured Platforms
Test which platforms the server successfully loaded credentials for:
```bash
curl http://localhost:8000/api/platforms
```
You should see `"status": "ready"` for any platform where you entered valid credentials.

### Step C: Trigger a Live Scrape
Let's tell the server to scrape Reddit and YouTube for the keyword "pothole".
Open a *new* terminal window, and run:
```bash
curl -X POST http://localhost:8000/api/scrape \
     -H "Content-Type: application/json" \
     -d '{
       "keywords": ["pothole", "water supply", "electricity"],
       "platforms": ["reddit", "youtube", "civic"],
       "max_results": 10
     }'
```
This will return a `job_id`. The server is now scraping those sites in the background.

### Step D: View the Results
Wait 10-20 seconds, then check the database to see what it found:
```bash
curl "http://localhost:8000/api/results?page_size=20"
```
Or view just Reddit results:
```bash
curl "http://localhost:8000/api/results/reddit"
```

---

## Using the Swagger UI
You can easily test all these endpoints directly in your browser without using `curl`.
Just open: **http://localhost:8000/docs**
Click on an endpoint, click **"Try it out"**, enter your data, and click **"Execute"**.
