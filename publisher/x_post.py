import os
import tweepy

def post_text(text: str):
    api_key = os.getenv("TWITTER_API_KEY")
    api_secret = os.getenv("TWITTER_API_SECRET")
    access_token = os.getenv("TWITTER_ACCESS_TOKEN")
    access_secret = os.getenv("TWITTER_ACCESS_SECRET")
    if not all([api_key, api_secret, access_token, access_secret]):
        raise RuntimeError("Twitter creds not set")
    auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
    api = tweepy.API(auth)
    api.update_status(status=text[:280])
