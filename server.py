from twitblob.easy import make_wsgi_app

CONFIG_FILE = "config.json"

CONFIG_DOCS = {
    'db_name': 'name of the MongoDB database to use for storage',
    'consumer_key': 'OAuth consumer key for Twitter',
    'consumer_secret': 'OAuth consumer secret for Twitter'
    }

if __name__ in ['__main__', '__builtin__']:
    import os
    import sys

    import simplejson as json
    import pymongo

    try:
        conn = pymongo.Connection()
    except Exception, e:
        print('Running this app requires a MongoDB server '
              'to be active on localhost at the default port.')
        sys.exit(1)

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

    app = make_wsgi_app(conn, **config)

    if __name__ == '__main__':
        from wsgiref.simple_server import make_server

        port = 8000
        httpd = make_server('', port, app)
        print "serving on port %d" % port
        httpd.serve_forever()
