import datetime

class MongoStorage(object):
    '''
    Note that this example code assumes a MongoDB server is active on
    localhost at the default port.

      >>> import pymongo
      >>> conn = pymongo.Connection()
      >>> coll = conn.twitblob_test_database.storage_test
      >>> coll.remove()

      >>> s = MongoStorage(coll)
      >>> 'blah' in s
      False
      >>> s['blah'] = {'foo': 1}
      >>> 'blah' in s
      True

      >>> s['blah']
      {u'foo': 1}
      >>> del s['blah']
      >>> 'blah' in s
      False
    '''

    def __init__(self, collection):
        self.collection = collection
        self.collection.ensure_index('name')

    def __contains__(self, name):
        doc = self.collection.find_one({'name': name})
        return (doc is not None)

    def __delitem__(self, name):
        if not name in self:
            raise KeyError(name)
        self.collection.remove({'name': name})

    def __getitem__(self, name):
        if not name in self:
            raise KeyError(name)
        return self.collection.find_one({'name': name})['value']

    def __setitem__(self, name, value):
        self.collection.update({'name': name},
                               {'name': name,
                                'value': value,
                                'date': datetime.datetime.utcnow()},
                               upsert=True)
