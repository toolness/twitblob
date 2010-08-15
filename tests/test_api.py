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

USER_IDS = {
    'bob': '1',
    'jane': '2'
    }

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
    return app.post(url, json.dumps(obj),
                    {'Content-Type': 'application/json'},
                    **kwargs)

def put_json(url, obj, **kwargs):
    return app.put(url, json.dumps(obj),
                   {'Content-Type': 'application/json'},
                   **kwargs)

def do_login(screen_name):
    assert screen_name in USER_IDS

    twitter.fake_screen_name = screen_name
    twitter.fake_user_id = USER_IDS[screen_name]
    resp = app.get('/login/fake-callback')
    return resp.headers['X-access-token']

@apptest
def test_login_contains_quota_info():
    twitter.fake_screen_name = 'bob'
    twitter.fake_user_id = USER_IDS['bob']
    resp = app.get('/login/fake-callback')
    assert '"quota": 20000' in resp

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
    resp.mustcontain('<script>window.opener.postMessage(')

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
def test_blobs_query_with_no_ids():
    resp = app.get('/blobs/?ids=foo', status=400)

@apptest
def test_get_user_list():
    post_json('/blobs/bob',
              {'token': do_login('bob'),
               'data': {'hai': 1}})
    resp = app.get('/who/')
    assert resp.json == [{'screen_name': 'bob',
                          'user_id': 1}]

@apptest
def test_blobs_query_with_nonexistent_ids():
    resp = app.get('/blobs/?ids=935234', status=200)
    assert resp.json == {}

@apptest
def test_blobs_query_with_good_ids():
    post_json('/blobs/bob',
              {'token': do_login('bob'),
               'data': {'hai': 1}})
    post_json('/blobs/jane',
              {'token': do_login('jane'),
               'data': {'there': 2}})
    # We'll include one nonexistent ID to make sure that works.
    resp = app.get('/blobs/?ids=1,2,439', status=200)
    assert resp.json == {'bob': {'hai': 1},
                         'jane': {'there': 2}}

@apptest
def test_cross_origin_support():
    resp = app.get('/blobs/', status=400)
    assert resp.headers['Access-Control-Allow-Origin'] == '*'
    assert resp.headers['Access-Control-Allow-Methods'] == ('OPTIONS,GET,'
                                                            'PUT,POST')
    assert resp.headers['Access-Control-Allow-Headers'] == 'Content-Type'

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
def test_post_json_blob_twice_updates():
    token = do_login('bob')
    post_json('/blobs/bob',
              {'token': token,
               'data': {'foo': 'bar'}})
    resp = app.get('/blobs/bob')
    assert resp.json == {'foo': 'bar'}

    post_json('/blobs/bob',
              {'token': token,
               'data': {'baz': 'um'}})
    resp = app.get('/blobs/bob')
    assert resp.json == {'foo': 'bar', 'baz': 'um'}

@apptest
def test_post_json_blob_then_put():
    token = do_login('bob')
    post_json('/blobs/bob',
              {'token': token,
               'data': {'foo': 'bar'}})
    resp = app.get('/blobs/bob')
    assert resp.json == {'foo': 'bar'}

    put_json('/blobs/bob',
             {'token': token,
              'data': {'meh': 1}})
    resp = app.get('/blobs/bob')
    assert resp.json == {'meh': 1}

@apptest
def test_expired_token():
    token = do_login('bob')
    TimeMachine.travel(api.db.token_lifetime)
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

@apptest
def test_options():
    result = {'done': False}

    def start_response(status, headers):
        if status != '200 OK':
            raise AssertionError()
        if ('Content-Length', '0') not in headers:
            raise AssertionError()
        result['done'] = True

    api.wsgi_app(
        environ={
            'PATH_INFO': '/',
            'REQUEST_METHOD': 'OPTIONS'
            },
        start_response=start_response
        )

    assert result['done']

@apptest
def test_feedback_with_no_impl():
    post_json('/feedback/',
              {'token': do_login('bob'),
               'message': 'o hai'},
              status=501)

@apptest
def test_feedback_with_impl():
    def fake_send_feedback(sender, message):
        return {'sender': sender, 'message': message}

    api.send_feedback = fake_send_feedback

    resp = post_json('/feedback/',
                     {'token': do_login('bob'),
                      'message': 'o hai'})

    assert resp.json == {'sender': 'bob',
                         'message': 'o hai'}

# TODO: Need tests for edge cases for feedback.
