## Twitblob ##

Twitblob is a Python-based WSGI app that provides a simple
cross-origin RESTful API giving all Twitter users a small amount of
public JSON blob storage on the host server.

For information on how to use an existing Twitblob server from a Web
page, see the [Web Documentation](http://toolness.github.com/twitblob/).

### Server Requirements ###

Running Twitblob on a server requires Python 2.5 or higher with the
`simplejson` and `oauth2` packages, MongoDB, and the Python MongoDB
driver.

Running the Twitblob test suite requires `nose` and `webtest`.

### Installation ###

Before proceeding, make sure you have a MongoDB server running on
localhost at the default port. This is currently required to run the
test suite and standalone development server.

Installing Twitblob on your server can be done by executing the
following at a shell prompt from the root of your checkout:

    python setup.py nosetests
    python setup.py build
    sudo python setup.py install

To run the development server, run `server.py`. It will provide
instructions on how to proceed.

To embed the Twitblob WSGI application into your web server, please
read the source code for `server.py`. Sorry this isn't easier right now!
