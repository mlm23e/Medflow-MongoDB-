class FakeCursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, field, direction):
        self.documents.sort(key=lambda item: item.get(field), reverse=direction < 0)
        return self

    def __aiter__(self):
        async def iterate():
            for document in self.documents:
                yield dict(document)
        return iterate()

    async def to_list(self, length):
        return [dict(document) for document in self.documents]


class FakeCollection:
    def __init__(self):
        self.documents = []
        self.find_calls = 0

    @staticmethod
    def matches(document, query):
        for key, expected in query.items():
            actual = document.get(key)
            if isinstance(expected, dict):
                if "$lt" in expected and not actual < expected["$lt"]:
                    return False
                if "$in" in expected and actual not in expected["$in"]:
                    return False
                if "$ne" in expected and actual == expected["$ne"]:
                    return False
            elif actual != expected:
                return False
        return True

    async def create_index(self, *args, **kwargs):
        return None

    async def find_one(self, query, projection=None):
        return next((dict(item) for item in self.documents if self.matches(item, query)), None)

    def find(self, query=None, projection=None):
        self.find_calls += 1
        query = query or {}
        return FakeCursor(item for item in self.documents if self.matches(item, query))

    async def insert_one(self, document):
        saved = dict(document)
        saved.setdefault("_id", len(self.documents) + 1)
        self.documents.append(saved)
        return saved

    async def update_one(self, query, update):
        for document in self.documents:
            if self.matches(document, query):
                document.update(update.get("$set", {}))
                for key, value in update.get("$max", {}).items():
                    document[key] = max(document.get(key, value), value)
                return type("UpdateResult", (), {"matched_count": 1})()
        return type("UpdateResult", (), {"matched_count": 0})()

    async def update_many(self, query, update):
        count = 0
        for document in self.documents:
            if self.matches(document, query):
                document.update(update.get("$set", {}))
                count += 1
        return type("UpdateResult", (), {"matched_count": count})()

    async def delete_one(self, query):
        for index, document in enumerate(self.documents):
            if self.matches(document, query):
                self.documents.pop(index)
                return type("DeleteResult", (), {"deleted_count": 1})()
        return type("DeleteResult", (), {"deleted_count": 0})()

    async def delete_many(self, query):
        before = len(self.documents)
        self.documents[:] = [item for item in self.documents if not self.matches(item, query)]
        return type("DeleteResult", (), {"deleted_count": before - len(self.documents)})()

    async def find_one_and_update(self, query, update, upsert=False, return_document=None):
        document = await self.find_one(query)
        if document is None:
            document = {"_id": query["_id"]}
            self.documents.append(document)
        for key, amount in update.get("$inc", {}).items():
            document[key] = document.get(key, 0) + amount
        return dict(document)


class FakeDatabase:
    def __init__(self):
        self.collections = {}
        self.command_error = None
        self.command_calls = 0

    def __getattr__(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]

    async def command(self, command):
        self.command_calls += 1
        if self.command_error is not None:
            raise self.command_error
        return {"ok": 1}
