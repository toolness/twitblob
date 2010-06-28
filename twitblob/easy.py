import oauth2 as oauth
from twitblob.api import TwitBlobApi
from twitblob.mongo_storage import MongoStorage
from twitblob.twitter_client import TwitterOauthClientApp

def make_wsgi_app(conn, db_name, consumer_key, consumer_secret, **kwargs):
    db = conn[db_name]

    consumer = oauth.Consumer(consumer_key, consumer_secret)

    twitter = TwitterOauthClientApp(
        consumer=consumer,
        oauth=oauth,
        request_tokens=MongoStorage(db.twitter_oauth_request_tokens)
        )

    api = TwitBlobApi(twitter=twitter, db=db, **kwargs)

    return api.wsgi_app
