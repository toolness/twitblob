import simplejson as json
import datetime

import pymongo
from webtest import TestApp
from twitblob.api import TwitBlobApi, gentoken

DBNAME = 'twitblob_test_database'

api = None
app = None
twitter = None
db = None

try:
    conn = pymongo.Connection()
except Exception, e:
    raise Exception('Running this test suite requires a MongoDB server '
                    'to be active on localhost at the default port.')

def apptest(func):
    def wrapper():
        g = globals()

        g['db'] = conn[DBNAME]

        for coll in [name for name in db.collection_names()
                     if not name.startswith('system.')]:
            db[coll].remove()

        g['twitter'] = FakeTwitter()
        g['api'] = TwitBlobApi(twitter=twitter, db=db,
                               utcnow=TimeMachine.utcnow,
                               gentoken=EntropyMachine.gentoken)
        g['app'] = TestApp(api.wsgi_app)

        func()

    wrapper.__name__ = func.__name__
    return wrapper

class EntropyMachine(object):
    next = []

    @classmethod
    def gentoken(klass):
        if klass.next:
            return klass.next.pop()
        return gentoken()

class TimeMachine(object):
    now = datetime.datetime(2010, 6, 17, 0, 32, 33, 985904)

    @classmethod
    def travel(klass, timedelta=None, *args, **kwargs):
        if timedelta is None:
            timedelta = datetime.timedelta(*args, **kwargs)

        klass.now += timedelta

    @classmethod
    def utcnow(klass):
        return klass.now

class FakeTwitter(object):
    def __call__(self, environ, start_response):
        if environ['PATH_INFO'] == '/':
            start_response('200 OK',
                           [('Content-Type', 'text/plain')])
            return ['redirect to twitter!']
        elif environ['PATH_INFO'] == '/fake-callback':
            environ['oauth.access_token'] = {
                'screen_name': self.fake_screen_name,
                'user_id': self.fake_user_id
                }
            return self.onsuccess(environ, start_response)
        raise AssertionError('unexpected path: %s' % environ['PATH_INFO'])

def post_json(url, obj, **kwargs):
    resp = app.post(url, json.dumps(obj),
                    {'Content-Type': 'application/json'},
                    **kwargs)

def do_login(screen_name):
    twitter.fake_screen_name = screen_name
    twitter.fake_user_id = '1'
    resp = app.get('/login/fake-callback')
    return resp.headers['X-access-token']

@apptest
def test_tokens_are_unique():
    EntropyMachine.next[:] = ['b', 'a', 'a', 'a', 'a']
    token1 = do_login('bob')
    token2 = do_login('jane')
    assert token1 == 'a'
    assert token2 == 'b'

@apptest
def test_login_returns_postmessage_code():
    twitter.fake_screen_name = 'bob'
    twitter.fake_user_id = '1'
    resp = app.get('/login/fake-callback')
    assert resp.headers['Content-Type'] == 'text/html'
    resp.mustcontain('<script>window.opener.postMessage(JSON.stringify(')

@apptest
def test_login():
    assert isinstance(do_login('bob'), basestring)

@apptest
def test_get_nonexistent_json_blob():
    resp = app.get('/blobs/nonexistent', status=404)

@apptest
def test_non_integer_content_length():
    resp = app.get('/blah', '', {'Content-Length': ''}, status=404)

@apptest
def test_trivial_404():
    resp = app.get('/blah', status=404)

@apptest
def test_blobs_400():
    resp = app.get('/blobs/', status=400)

@apptest
def test_blobs_query_with_bad_ids():
    resp = app.get('/blobs/?ids=foo', status=400)

@apptest
def test_blobs_query_with_good_ids():
    # TODO: Need to implement this and return something other than 501.
    resp = app.get('/blobs/?ids=1,2,3', status=501)

@apptest
def test_cross_origin_support():
    resp = app.get('/blobs/', status=400)
    assert resp.headers['Access-Control-Allow-Origin'] == '*'

@apptest
def test_post_json_blob_with_invalid_token():
    post_json('/blobs/bob',
              {'token': 'bad token',
               'data': {}},
              status=403)

@apptest
def test_post_json_blob_with_unauthorized_token():
    post_json('/blobs/bob',
              {'token': do_login('jane'),
               'data': {}},
              status=403)

@apptest
def test_massive_body():
    post_json('/blobs/bob',
              {'data': {'foo': '1' * api.max_body_size}},
              status=413)

@apptest
def test_post_json_blob_with_no_token():
    post_json('/blobs/bob',
              {'data': {}},
              status=403)

@apptest
def test_post_malformed_json_blob():
    resp = app.post(
        '/blobs/bob', 'bleh',
        {'Content-Type': 'application/json'},
        status=400
        )

@apptest
def test_post_json_blob_with_no_data():
    post_json('/blobs/bob',
              {'token': do_login('bob')},
              status=400)

@apptest
def test_post_json_blob_with_invalid_data():
    post_json('/blobs/bob',
              {'token': do_login('bob'),
               'data': 'i am not an object'},
              status=400)

@apptest
def test_post_json_blob():
    blob = {'talks': {'0': 0, '1': 5}}
    post_json('/blobs/bob',
              {'token': do_login('bob'),
               'data': blob})
    resp = app.get('/blobs/bob')
    assert resp.json == blob

@apptest
def test_expired_token():
    token = do_login('bob')
    TimeMachine.travel(api.token_lifetime)
    post_json('/blobs/bob',
              {'token': token,
               'data': {}},
              status=403)

@apptest
def test_forged_token():
    post_json('/blobs/bob',
              {'token': '4c197e4a68fb2f095a000000',
               'data': {}},
              status=403)
