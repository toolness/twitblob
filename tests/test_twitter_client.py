import minimock

from twitblob.twitter_client import TwitterOauthClientApp

class Mock(minimock.Mock):
    def __repr__(self):
        return "<Mock %s>" % self.mock_name

def app(request_tokens=None):
    if request_tokens is None:
        request_tokens = {}
    consumer = 'mock consumer'
    oauth = Mock('oauth')
    onsuccess = Mock('onsuccess')
    toc = TwitterOauthClientApp(consumer, oauth,
                                request_tokens, onsuccess)
    return (consumer, oauth, onsuccess, toc)

def test_404():
    """
    >>> _, _, _, toc = app()
    >>> environ = dict(PATH_INFO='/blah', QUERY_STRING='')
    >>> toc(environ, Mock('start_response'))
    Called start_response('404 Not Found', [('Content-Type', 'text/plain')])
    ['path not found: /blah']
    """

    pass

def test_request_redirect():
    """
    >>> consumer, oauth, _, toc = app()
    >>> client = Mock('client')
    >>> client.request.mock_returns = (
    ...   {'status': '200'},
    ...   'oauth_token=token&oauth_token_secret=secret&'
    ...   'oauth_callback_confirmed=true'
    ... )
    >>> oauth.Client.mock_returns = client
    >>> environ = dict(PATH_INFO='/', QUERY_STRING='', SERVER_NAME='foo.com', SERVER_PORT='80')
    >>> environ['wsgi.url_scheme'] = 'http'
    >>> toc(environ, Mock('start_response'))
    Called oauth.Client('mock consumer')
    Called client.request(
        'https://api.twitter.com/oauth/request_token?oauth_callback=http%3A%2F%2Ffoo.com%2Fcallback',
        'GET')
    Called start_response(
        '302 Found',
        [('Location', 'https://api.twitter.com/oauth/authorize?oauth_token=token')])
    []
    """

    pass

def test_callback():
    """
    >>> storage = {'token': {'oauth_token': 'token', 'oauth_token_secret': 'secret'}}
    >>> consumer, oauth, onsuccess, toc = app(storage)
    >>> client = Mock('client')
    >>> client.request.mock_returns = (
    ...   {'status': '200'},
    ...   'oauth_token=token&oauth_token_secret=secret&'
    ...   'user_id=userid&screen_name=bob'
    ... )
    >>> oauth.Client.mock_returns = client
    >>> token = Mock('token')
    >>> oauth.Token.mock_returns = token
    >>> environ = dict(
    ...   PATH_INFO='/callback',
    ...   QUERY_STRING='oauth_token=token&oauth_verifier=verifier',
    ...   SERVER_NAME='foo.com', SERVER_PORT='80'
    ... )
    >>> environ['wsgi.url_scheme'] = 'http'
    >>> onsuccess.mock_returns = ['success']
    >>> toc(environ, Mock('start_response'))
    Called oauth.Token('token', 'secret')
    Called token.set_verifier('verifier')
    Called oauth.Client('mock consumer', <Mock token>)
    Called client.request('https://api.twitter.com/oauth/access_token', 'POST')
    Called onsuccess(
        {'SERVER_NAME': 'foo.com', 'wsgi.url_scheme': 'http', 'PATH_INFO': '/callback', 'SERVER_PORT': '80', 'oauth.access_token': {'oauth_token_secret': 'secret', 'user_id': 'userid', 'oauth_token': 'token', 'screen_name': 'bob'}, 'QUERY_STRING': 'oauth_token=token&oauth_verifier=verifier'},
        <Mock start_response>)
    ['success']
    """

    pass

if __name__ == '__main__':
    import doctest
    doctest.testmod()
    print "done running tests."
