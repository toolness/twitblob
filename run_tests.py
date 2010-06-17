#! /usr/bin/env python

if __name__ == '__main__':
    import nose
    import sys
    import pymongo

    try:
        conn = pymongo.Connection()
        conn.end_request()
    except Exception, e:
        print('Running this test suite requires a MongoDB server '
              'to be active on localhost at the default port.')
        sys.exit(1)

    nose.run(env={'NOSE_WITH_DOCTEST': 1,
                  'NOSE_DOCTEST_TESTS': 1})
