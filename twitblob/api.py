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

class BlobRequest(object):
    def __init__(self, api, environ, start_response):
        self.api = api
        self.environ = environ
        self.start_response = start_response
        self.path = environ['PATH_INFO']
        self.method = environ['REQUEST_METHOD']
        self.qargs = dict(parse_qsl(self.environ.get('QUERY_STRING', '')))

        try:
            self.length = int(environ.get('CONTENT_LENGTH', '0'))
        except ValueError:
            self.length = 0

    def json_response(self, status, obj):
        self.start_response(status,
                            [('Content-Type', 'application/json')])
        return [json.dumps(obj)]

    def get_body(self):
        f = self.environ['wsgi.input']
        try:
            obj = json.loads(f.read(self.length))
        except ValueError:
            return (None, None)
        if 'token' in obj:
            return (obj, self.api.get_token(obj['token']))
        return (obj, None)

    def serve_blob(self):
        if self.path == '/blobs/':
            if 'ids' in self.qargs:
                try:
                    ids = [int(strid)
                           for strid in self.qargs['ids'].split(",")]
                except ValueError:
                    return self.json_response('400 Bad Request',
                                              {'error': 'invalid ids'})
                return self.json_response('200 OK',
                                          self.api.get_blobs_for_ids(ids))
            return self.json_response('400 Bad Request',
                                      {'error': 'need query args'})
        user = self.path.split('/')[2]
        if self.method in ['POST', 'PUT']:
            obj, token = self.get_body()
            if obj is None:
                return self.json_response(
                    '400 Bad Request',
                    {'error': 'error parsing JSON body'}
                    )
            if not (isinstance(obj, dict) and 
                    isinstance(obj.get('data'), dict)):
                return self.json_response(
                    '400 Bad Request',
                    {'error': 'body must contain "data" object'}
                    )
            if token and token['screen_name'] == user:
                if self.method == 'POST':
                    self.api.update_user(token=token, data=obj['data'])
                else:
                    self.api.replace_user(token=token, data=obj['data'])
                return self.json_response('200 OK', {'success': True})
            else:
                return self.json_response(
                    '403 Forbidden',
                    {'error': 'Missing or invalid auth token'}
                    )
        elif self.method == 'GET':
            blob = self.api.get_blob(user)
            if blob is None:
                return self.json_response('404 Not Found',
                                          {'error': 'blob does not exist'})
            return self.json_response('200 OK', blob)

    def post_feedback(self):
        if self.method != 'POST':
            return self.json_response(
                '405 Method Not Allowed',
                {'error': 'unsupported method: %s' % self.method}
                )
        obj, token = self.get_body()
        if obj is None:
            return self.json_response(
                '400 Bad Request',
                {'error': 'error parsing JSON body'}
                )
        if not (isinstance(obj, dict) and 
                isinstance(obj.get('message'), basestring)):
            return self.json_response(
                '400 Bad Request',
                {'error': 'body must contain "message" string'}
                )
        if not token:
            return self.json_response(
                '403 Forbidden',
                {'error': 'Missing or invalid auth token'}
                )
        if not self.api.send_feedback:
            return self.json_response(
                '501 Not Implemented',
                {'error': 'feedback mechanism not implemented'}
                )
        result = self.api.send_feedback(sender=token['screen_name'],
                                        message=obj['message'])
        return self.json_response('200 OK', result)

    def process(self):
        if self.length > self.api.max_body_size:
            return self.json_response('413 Request Entity Too Large',
                                      {'error': 'too big'})

        if self.path.startswith('/blobs/'):
            return self.serve_blob()
        if self.path == '/who/':
            return self.json_response('200 OK', self.api.get_user_list())
        if self.path == '/feedback/':
            return self.post_feedback()

        self.start_response('404 Not Found',
                            [('Content-Type', 'text/plain')])
        return ['unknown path: %s' % self.path]

class TwitBlobApi(object):
    def __init__(self, twitter, db, max_body_size=DEFAULT_MAX_BODY_SIZE,
                 token_lifetime=DEFAULT_TOKEN_LIFETIME,
                 utcnow=datetime.datetime.utcnow,
                 gentoken=gentoken,
                 send_feedback=None):
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
        self.send_feedback = send_feedback

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

    def get_token(self, tokid):
        token = self.db.auth_tokens.find_one({'id': tokid})
        if (token is not None and
            self.utcnow() - token['date'] > self.token_lifetime):
            token = None
            self.db.auth_tokens.remove({'id': tokid})
        return token

    def get_user_list(self):
        return [{'screen_name': blob['screen_name'],
                 'user_id': blob['user_id']}
                for blob in self.db.blobs.find()]

    def get_blobs_for_ids(self, ids):
        blobs = {}
        # TODO: This may be really slow because of the
        # many requests we're making to the DB. Shouldn't
        # be hard to optimize, though.
        for intid in ids:
            blob = self.db.blobs.find_one({'user_id': intid})
            if blob is not None:
                blobs[blob['screen_name']] = blob['data']
        return blobs

    def update_user(self, token, data):
        blob = self.db.blobs.find_one({'screen_name': token['screen_name']})
        if blob is not None:
            for name in data:
                blob['data'][name] = data[name]
            data = blob['data']
        self.replace_user(token, data)

    def replace_user(self, token, data):
        self.db.blobs.update({'user_id': token['user_id']},
                             {'screen_name': token['screen_name'],
                              'user_id': token['user_id'],
                              'data': data},
                             upsert=True)

    def get_blob(self, screen_name):
        blob = self.db.blobs.find_one({'screen_name': screen_name})
        if blob is not None:
            return blob['data']
        return None

    @allow_cross_origin
    def wsgi_app(self, environ, start_response):
        if environ['PATH_INFO'].startswith('/login/'):
            wsgiref.util.shift_path_info(environ)
            return self.twitter(environ, start_response)

        request = BlobRequest(self, environ, start_response)
        return request.process()
