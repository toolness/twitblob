import json
import wsgiref.util

from pymongo.objectid import ObjectId
from pymongo.errors import InvalidId

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

        def get_body():
            f = environ['wsgi.input']
            obj = json.loads(f.read(int(environ['CONTENT_LENGTH'])))
            if 'token' in obj:
                try:
                    objid = ObjectId(obj['token'])
                except InvalidId:
                    return (obj, None)
                return (obj, self.db.auth_tokens.find_one(objid))
            else:
                return (obj, None)

        def json_response(status, obj):
            start_response(status,
                           [('Content-Type', 'application/json')])
            return [json.dumps(obj)]

        if path.startswith('/blobs/'):
            user = path.split('/')[2]
            if method == 'POST':
                obj, token = get_body()
                if token and token['screen_name'] == user:
                    self.db.blobs.update({'screen_name': user},
                                         {'screen_name': user, 'data': obj['data']},
                                         upsert=True)
                    return json_response('200 OK', {'success': True})
                else:
                    return json_response(
                        '403 Forbidden',
                        {'error': 'Missing or invalid auth token'}
                        )
            elif method == 'GET':
                blob = self.db.blobs.find_one({'screen_name': user})
                if blob is None:
                    return json_response('404 Not Found',
                                         {'error': 'blob does not exist'})
                return json_response('200 OK', blob['data'])

        start_response('404 Not Found',
                       [('Content-Type', 'text/plain')])
        return ['unknown path: %s' % path]
