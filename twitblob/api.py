import simplejson as json
import wsgiref.util
import datetime
from cgi import parse_qsl
from base64 import urlsafe_b64encode
from os import urandom

DEFAULT_MAX_BODY_SIZE = 20000

# By default, auth tokens last a fortnight.
DEFAULT_TOKEN_LIFETIME = datetime.timedelta(days=14)

def allow_cross_origin(func):
    header = ('Access-Control-Allow-Origin', '*')
    def wsgi_wrapper(self, environ, start_response):
        def new_start_response(status, headers):
            start_response(status, headers + [header])
        return func(self, environ, new_start_response)
    return wsgi_wrapper

def gentoken():
    # Generate a 256-bit key, but add a byte so we don't have
    # an annoying '=' in the string.
    return urlsafe_b64encode(urandom(256/8+1))

class TwitBlobApi(object):
    def __init__(self, twitter, db, max_body_size=DEFAULT_MAX_BODY_SIZE,
                 token_lifetime=DEFAULT_TOKEN_LIFETIME,
                 utcnow=datetime.datetime.utcnow,
                 gentoken=gentoken):
        twitter.onsuccess = self.__twitter_onsuccess
        self.twitter = twitter
        self.db = db
        self.db.blobs.ensure_index('screen_name')
        self.db.blobs.ensure_index('user_id')
        self.db.auth_tokens.ensure_index('id')
        self.utcnow = utcnow
        self.gentoken = gentoken
        self.token_lifetime = token_lifetime
        self.max_body_size = max_body_size

    def __twitter_onsuccess(self, environ, start_response):
        token_id = self.gentoken()
        while self.db.auth_tokens.find_one({'id': token_id}):
            token_id = self.gentoken()
        token = {
            'id': token_id,
            'screen_name': environ['oauth.access_token']['screen_name'],
            'user_id': int(environ['oauth.access_token']['user_id']),
            'date': self.utcnow()
            }
        self.db.auth_tokens.insert(token)
        start_response('200 OK',
                       [('Content-Type', 'text/html'),
                        ('X-access-token', token['id'])])
        client_token = {
            'token': token['id'],
            'screen_name': token['screen_name'],
            'user_id': token['user_id']
            }
        script = "window.opener.postMessage(JSON.stringify(%s), '*');" % (
            json.dumps(client_token)
            )
        return ['<script>%s</script>' % script]

    @allow_cross_origin
    def wsgi_app(self, environ, start_response):
        path = environ['PATH_INFO']
        method = environ['REQUEST_METHOD']

        if path.startswith('/login/'):
            wsgiref.util.shift_path_info(environ)
            return self.twitter(environ, start_response)

        def json_response(status, obj):
            start_response(status,
                           [('Content-Type', 'application/json')])
            return [json.dumps(obj)]

        def err_404():
            start_response('404 Not Found',
                           [('Content-Type', 'text/plain')])
            return ['unknown path: %s' % path]

        try:
            length = int(environ.get('CONTENT_LENGTH', '0'))
        except ValueError:
            length = 0

        if length > self.max_body_size:
            return json_response('413 Request Entity Too Large',
                                 {'error': 'too big'})

        def get_body():
            f = environ['wsgi.input']
            try:
                obj = json.loads(f.read(length))
            except ValueError:
                return (None, None)
            if 'token' in obj:
                token = self.db.auth_tokens.find_one({'id': obj['token']})
                if token is None:
                    return (obj, None)
                if self.utcnow() - token['date'] > self.token_lifetime:
                    token = None
                    self.db.auth_tokens.remove({'id': obj['token']})
                return (obj, token)
            else:
                return (obj, None)

        if path.startswith('/blobs/'):
            if path == '/blobs/':
                qargs = dict(parse_qsl(environ.get('QUERY_STRING', '')))
                if 'ids' in qargs:
                    try:
                        ids = [int(strid)
                               for strid in qargs['ids'].split(",")]
                        blobs = {}
                        # TODO: This may be really slow because of the
                        # many requests we're making to the DB. Shouldn't
                        # be hard to optimize, though.
                        for intid in ids:
                            blob = self.db.blobs.find_one({'user_id': intid})
                            if blob is not None:
                                blobs[blob['screen_name']] = blob['data']
                        return json_response('200 OK', blobs)
                    except ValueError:
                        return json_response('400 Bad Request',
                                             {'error': 'invalid ids'})
                return json_response('400 Bad Request',
                                     {'error': 'need query args'})
            user = path.split('/')[2]
            if method == 'POST':
                obj, token = get_body()
                if obj is None:
                    return json_response(
                        '400 Bad Request',
                        {'error': 'error parsing JSON body'}
                        )
                if not (isinstance(obj, dict) and 
                        isinstance(obj.get('data'), dict)):
                    return json_response(
                        '400 Bad Request',
                        {'error': 'body must contain "data" object'}
                        )
                if token and token['screen_name'] == user:
                    self.db.blobs.update({'user_id': token['user_id']},
                                         {'screen_name': user,
                                          'user_id': token['user_id'],
                                          'data': obj['data']},
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

        return err_404()
