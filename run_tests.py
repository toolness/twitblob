#! /usr/bin/env python

if __name__ == '__main__':
    import nose

    nose.run(env={'NOSE_WITH_DOCTEST': 1,
                  'NOSE_DOCTEST_TESTS': 1})
