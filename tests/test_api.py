import json

import pymongo
from webtest import TestApp
from mozsummit.api import MozSummitApi

DBNAME = 'mozsummit_test_database'

api = None
app = None
twitter = None
db = None

conn = pymongo.Connection()

def TODO_apptest(func):
    def wrapper():
        pass

    wrapper.__name__ = func.__name__
    return wrapper
    
def apptest(func):
    def wrapper():
        g = globals()

        g['db'] = conn[DBNAME]

        for coll in [name for name in db.collection_names()
                     if not name.startswith('system.')]:
            db[coll].remove()

        g['twitter'] = FakeTwitter()
        g['api'] = MozSummitApi(twitter=twitter, db=db)
        g['app'] = TestApp(api.wsgi_app)

        func()

    wrapper.__name__ = func.__name__
    return wrapper

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

def post_json(url, obj, ensure_success=True):
    resp = app.post(url, json.dumps(obj),
                    {'Content-Type': 'application/json'})
    if resp.json != {'success': True}:
        raise AssertionError(repr(resp.json))

def do_login(screen_name):
    twitter.fake_screen_name = screen_name
    twitter.fake_user_id = '1'
    resp = app.get('/login/fake-callback')
    return resp.headers['X-access-token']

@apptest
def test_login():
    assert isinstance(do_login('bob'), basestring)

@apptest
def test_post_json_blob():
    blob = {'talks': {'0': 0, '1': 5}}
    post_json('/users/bob',
              {'token': do_login('bob'),
               'data': blob})
    resp = app.get('/users/bob')
    assert resp.json == blob
