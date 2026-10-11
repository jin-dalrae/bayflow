from backend.app.store import Store


def test_read_write_failure_never_reports_connected(monkeypatch):
    from backend.app import store as module

    class Admin:
        def command(self, name):
            return {"ok": 1}

    class Collection:
        def insert_one(self, doc):
            raise PermissionError("write denied")

    class Database:
        def __getitem__(self, name):
            return Collection()

    class Client:
        admin = Admin()

        def __getitem__(self, name):
            return Database()

    monkeypatch.setenv("MONGODB_URI", "mongodb+srv://not-a-real-test-cluster.example")
    monkeypatch.setattr(module, "MongoClient", lambda *args, **kwargs: Client())
    store = Store()
    assert store.status()["connected"] is False
    assert store.db is None
    assert store.status()["eligible"] is False
