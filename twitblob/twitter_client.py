import simplejson as json
from cgi import parse_qsl
import urllib
from wsgiref.util import application_uri

class TwitterOauthClientApp(object):
    base_url = 'https://api.twitter.com/oauth/'
    request_token_url = base_url + 'request_token'
    access_token_url = base_url + 'access_token'
    authorize_url = base_url + 'authorize'

    def __init__(self, consumer, oauth, request_tokens, onsuccess=None):
        self.oauth = oauth
        self.consumer = consumer
        self.onsuccess = onsuccess
        self.request_tokens = request_tokens

    def __call__(self, environ, start_response):
        path = environ['PATH_INFO']
        qs = environ['QUERY_STRING']

        if path == '/':
            # Step 1: Get a request token. This is a temporary token that is used for 
            # having the user authorize an access token and to sign the request to obtain 
            # said access token.

            appuri = application_uri(environ)
            if not appuri.endswith('/'):
                appuri += '/'
            oauth_callback = '%scallback' % appuri

            url = '%s?%s' % (
                self.request_token_url,
                urllib.urlencode({'oauth_callback': oauth_callback})
                )
            client = self.oauth.Client(self.consumer)
            resp, content = client.request(url, "GET")
            if resp['status'] != '200':
                raise Exception("Invalid response %s." % resp['status'])

            request_token = dict(parse_qsl(content))

            if ('oauth_callback_confirmed' not in request_token or
                request_token['oauth_callback_confirmed'] != 'true'):
                raise Exception("Oauth callback must be confirmed.")

            self.request_tokens[request_token['oauth_token']] = request_token

            # Step 2: Redirect to the provider.

            redirect_url = "%s?oauth_token=%s" % (self.authorize_url,
                                                  request_token['oauth_token'])
            start_response('302 Found',
                           [('Location', redirect_url)])
            return []
        elif path == '/callback':
            qsdict = dict(parse_qsl(qs))

            if qsdict['oauth_token'] not in self.request_tokens:
                raise Exception('invalid token: %s' % self.request_tokens)

            request_token = self.request_tokens[qsdict['oauth_token']]
            del self.request_tokens[qsdict['oauth_token']]

            token = self.oauth.Token(request_token['oauth_token'],
                                     request_token['oauth_token_secret'])
            token.set_verifier(qsdict['oauth_verifier'])
            client = self.oauth.Client(self.consumer, token)
            resp, content = client.request(self.access_token_url, "POST")
            if resp['status'] != '200':
                raise Exception("Invalid response %s." % resp['status'])
            access_token = dict(parse_qsl(content))
            environ['oauth.access_token'] = access_token
            return self.onsuccess(environ, start_response)

        start_response('404 Not Found',
                       [('Content-Type', 'text/plain')])
        return ['path not found: %s' % path]
