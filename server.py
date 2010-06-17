import os
import sys
import json

import oauth2 as oauth
import pymongo
from twitblob.api import TwitBlobApi
from twitblob.mongo_storage import MongoStorage
from twitblob.twitter_client import TwitterOauthClientApp

try:
    conn = pymongo.Connection()
except Exception, e:
    print('Running this app requires a MongoDB server '
          'to be active on localhost at the default port.')
    sys.exit(1)

CONFIG_FILE = "config.json"

CONFIG_DOCS = {
    'db': 'name of the MongoDB database to use for storage',
    'consumer_key': 'OAuth consumer key for Twitter',
    'consumer_secret': 'OAuth consumer secret for Twitter'
    }

if not os.path.exists(CONFIG_FILE):
    print("%s not found. Please create a JSON-formatted file with "
          "this name and the following keys:\n" % CONFIG_FILE)
    for name, text in CONFIG_DOCS.items():
        print "  %-15s - %s" % (name, text)
    print
    sys.exit(1)

config = json.loads(open(CONFIG_FILE).read())

missing_keys = [name for name in CONFIG_DOCS
                if name not in config]

if missing_keys:
    print("Your %s file does not contain the following "
          "keys:\n" % CONFIG_FILE)
    for name in missing_keys:
        print "  %-15s - %s" % (name, CONFIG_DOCS[name])
    print
    sys.exit(1)

db = conn[config['db']]

consumer = oauth.Consumer(config['consumer_key'],
                          config['consumer_secret'])

twitter = TwitterOauthClientApp(
    consumer=consumer,
    oauth=oauth,
    request_tokens=MongoStorage(db.twitter_oauth_request_tokens)
    )

api = TwitBlobApi(twitter=twitter, db=db)

app = api.wsgi_app

if __name__ == '__main__':
    from wsgiref.simple_server import make_server
    
    port = 8000
    httpd = make_server('', port, app)
    print "serving on port %d" % port
    httpd.serve_forever()
