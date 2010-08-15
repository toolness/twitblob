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
    aca_headers = [
        ('Access-Control-Allow-Origin', '*'),
        ('Access-Control-Allow-Methods', 'OPTIONS,GET,PUT,POST'),
        ('Access-Control-Allow-Headers', 'Content-Type')
        ]
    def wsgi_wrapper(self, environ, start_response):
        def new_start_response(status, headers):
            start_response(status, headers + aca_headers)
        return func(self, environ, new_start_response)
    return wsgi_wrapper

def gentoken():
    # Generate a 256-bit key, but add a byte so we don't have
    # an annoying '=' in the string.
    return urlsafe_b64encode(urandom(256/8+1))

class Request(object):
    def __init__(self, environ, start_response):
        self.environ = environ
        self.start_response = start_response
        self.path = environ['PATH_INFO']
        self.method = environ['REQUEST_METHOD']
        self.qargs = dict(parse_qsl(self.environ.get('QUERY_STRING', '')))

        try:
            self.length = int(environ.get('CONTENT_LENGTH', '0'))
        except ValueError:
            self.length = 0

    def json_response(self, obj, status='200 OK'):
        self.start_response(status,
                            [('Content-Type', 'application/json')])
        return [json.dumps(obj)]

    def json_error(self, error, status='400 Bad Request'):
        return self.json_response({'error': error}, status)

class TwitBlobDb(object):
    def __init__(self, db, token_lifetime=DEFAULT_TOKEN_LIFETIME,
                 utcnow=datetime.datetime.utcnow, gentoken=gentoken):
        self.db = db
        self.db.blobs.ensure_index('screen_name')
        self.db.blobs.ensure_index('user_id')
        self.db.auth_tokens.ensure_index('id')
        self.utcnow = utcnow
        self.gentoken = gentoken
        self.token_lifetime = token_lifetime

    def make_token(self, screen_name, user_id):
        token_id = self.gentoken()
        while self.db.auth_tokens.find_one({'id': token_id}):
            token_id = self.gentoken()
        token = {
            'id': token_id,
            'screen_name': screen_name,
            'user_id': user_id,
            'date': self.utcnow()
            }
        self.db.auth_tokens.insert(token)
        return token

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

class TwitBlobApi(object):
    def __init__(self, twitter, db, max_body_size=DEFAULT_MAX_BODY_SIZE,
                 send_feedback=None, **kwargs):
        twitter.onsuccess = self.__twitter_onsuccess
        self.twitter = twitter
        self.db = TwitBlobDb(db, **kwargs)
        self.max_body_size = max_body_size
        self.send_feedback = send_feedback

    def __twitter_onsuccess(self, environ, start_response):
        token = self.db.make_token(
            environ['oauth.access_token']['screen_name'],
            int(environ['oauth.access_token']['user_id'])
            )
        start_response('200 OK',
                       [('Content-Type', 'text/html'),
                        ('X-access-token', token['id'])])
        client_token = {
            'token': token['id'],
            'screen_name': token['screen_name'],
            'user_id': token['user_id'],
            'quota': self.max_body_size
            }
        script = "window.opener.postMessage(%s, '*');" % (
            repr(str(json.dumps(client_token)))
            )
        return ['<script>%s</script>' % script]

    def get_body(self, req):
        f = req.environ['wsgi.input']
        try:
            obj = json.loads(f.read(req.length))
        except ValueError:
            return (None, None)
        if 'token' in obj:
            return (obj, self.db.get_token(obj['token']))
        return (obj, None)

    def serve_blob(self, req):
        if req.path == '/blobs/':
            if 'ids' in req.qargs:
                try:
                    ids = [int(strid)
                           for strid in req.qargs['ids'].split(",")]
                except ValueError:
                    return req.json_error('invalid ids')
                return req.json_response(self.db.get_blobs_for_ids(ids))
            return req.json_error('need query args')
        user = req.path.split('/')[2]
        if req.method in ['POST', 'PUT']:
            obj, token = self.get_body(req)
            if obj is None:
                return req.json_error('error parsing JSON body')
            if not (isinstance(obj, dict) and 
                    isinstance(obj.get('data'), dict)):
                return req.json_error('body must contain "data" object')
            if token and token['screen_name'] == user:
                if req.method == 'POST':
                    self.db.update_user(token=token, data=obj['data'])
                else:
                    self.db.replace_user(token=token, data=obj['data'])
                return req.json_response({'success': True})
            else:
                return req.json_error('Missing or invalid auth token',
                                      status='403 Forbidden')
        elif req.method == 'GET':
            blob = self.db.get_blob(user)
            if blob is None:
                return req.json_error('blob does not exist',
                                      status='404 Not Found')
            return req.json_response(blob)

    def post_feedback(self, req):
        if req.method != 'POST':
            return req.json_error('unsupported method: %s' % req.method,
                                  status='405 Method Not Allowed')
        obj, token = self.get_body(req)
        if obj is None:
            return req.json_error('error parsing JSON body')
        if not (isinstance(obj, dict) and 
                isinstance(obj.get('message'), basestring)):
            return req.json_error('body must contain "message" string')
        if not token:
            return req.json_error('Missing or invalid auth token',
                                  status='403 Forbidden')
        if not self.send_feedback:
            return req.json_error('feedback mechanism not implemented',
                                  status='501 Not Implemented')
        result = self.send_feedback(sender=token['screen_name'],
                                    message=obj['message'])
        return req.json_response(result)

    @allow_cross_origin
    def wsgi_app(self, environ, start_response):
        if environ['PATH_INFO'].startswith('/login/'):
            wsgiref.util.shift_path_info(environ)
            return self.twitter(environ, start_response)

        req = Request(environ, start_response)

        if req.length > self.max_body_size:
            return req.json_error('too big',
                                  status='413 Request Entity Too Large')

        if req.method == "OPTIONS":
            start_response('200 OK', [('Content-Length', '0')])
            return []

        if req.path.startswith('/blobs/'):
            return self.serve_blob(req)
        if req.path == '/who/':
            return req.json_response(self.db.get_user_list())
        if req.path == '/feedback/':
            return self.post_feedback(req)

        start_response('404 Not Found',
                       [('Content-Type', 'text/plain')])
        return ['unknown path: %s' % req.path]
