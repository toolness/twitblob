import json
import wsgiref.util

from pymongo.objectid import ObjectId

class MozSummitApi(object):
    def __init__(self, twitter, db):
        twitter.onsuccess = self.__twitter_onsuccess
        self.twitter = twitter
        self.db = db
        self.db.blobs.ensure_index('screen_name')

    def __twitter_onsuccess(self, environ, start_response):
        token = {
            'screen_name': environ['oauth.access_token']['screen_name'],
            'user_id': environ['oauth.access_token']['user_id']
            }
        hexid = str(self.db.auth_tokens.insert(token))
        start_response('200 OK',
                       [('Content-Type', 'text/plain'),
                        ('X-access-token', hexid)])
        return ['TODO: window.postMessage() new token.']

    def wsgi_app(self, environ, start_response):
        path = environ['PATH_INFO']
        method = environ['REQUEST_METHOD']

        if path.startswith('/login/'):
            wsgiref.util.shift_path_info(environ)
            return self.twitter(environ, start_response)

        if path.startswith('/users/'):
            user = path.split('/')[2]
            if method == 'POST':
                f = environ['wsgi.input']
                obj = json.loads(f.read(int(environ['CONTENT_LENGTH'])))
                token = self.db.auth_tokens.find_one(ObjectId(obj['token']))
                if token['screen_name'] == user:
                    self.db.blobs.update({'screen_name': user},
                                         {'screen_name': user, 'data': obj['data']},
                                         upsert=True)
                    start_response('200 OK',
                                   [('Content-Type', 'application/json')])
                    return [json.dumps({'success': True})]
                else:
                    # TODO: return 'unauthorized' failure
                    pass
            elif method == 'GET':
                blob = self.db.blobs.find_one({'screen_name': user})
                start_response('200 OK',
                               [('Content-Type', 'application/json')])
                return [json.dumps(blob['data'])]

        start_response('404 Not Found',
                       [('Content-Type', 'text/plain')])
        return ['unknown path: %s' % path]
