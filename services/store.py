"""
File-backed async collection store.

Implements the subset of the motor API this server actually uses, so the same
handlers work whether the backend is MongoDB or a local JSON file:

    find_one, find (+ .sort / .to_list), insert_one, update_one,
    delete_one, count_documents, distinct
    update operators: $set, $inc, $unset
    queries: equality only (dot-notation paths supported)

This exists so the server can run without provisioning MongoDB. Data lives in
one JSON file per collection and is rewritten atomically on each write, which
is fine for the single-worker private-server case.

Note: on free hosting the container filesystem is ephemeral, so this store
resets on redeploy unless a persistent disk is mounted.
"""

import asyncio
import json
import uuid
from pathlib import Path


# ─── document helpers ────────────────────────────────────────────────────

def _get_path(doc, path):
    """Read a dot-notation path, returning None when any segment is missing."""
    current = doc
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _set_path(doc, path, value):
    parts = path.split(".")
    current = doc
    for part in parts[:-1]:
        nxt = current.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            current[part] = nxt
        current = nxt
    current[parts[-1]] = value


def _unset_path(doc, path):
    parts = path.split(".")
    current = doc
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return
        current = current[part]
    if isinstance(current, dict):
        current.pop(parts[-1], None)


def _matches(doc, query):
    """Equality match. A nested dict/list value compares as a whole subtree."""
    for key, wanted in (query or {}).items():
        actual = _get_path(doc, key)
        if actual is None and wanted is None:
            continue
        if actual != wanted:
            return False
    return True


def _project(doc, projection):
    """Apply MongoDB projection semantics: all-1 means include-only."""
    if not projection:
        return json.loads(json.dumps(doc))  # deep copy, matches Motor isolation
    has_include = any(k != "_id" and v for k, v in projection.items())
    if has_include:
        out = {}
        if projection.get("_id", 0) and "_id" in doc:
            out["_id"] = doc["_id"]
        for key, value in projection.items():
            if key != "_id" and value and key in doc:
                out[key] = doc[key]
        return out
    # Exclusion projection: drop only the fields explicitly mapped to 0.
    return {k: v for k, v in doc.items() if projection.get(k, 1) != 0}


def _apply_update(doc, update):
    """Apply $set / $inc / $unset in place."""
    for operator, fields in (update or {}).items():
        if operator == "$set":
            for key, value in fields.items():
                _set_path(doc, key, value)
        elif operator == "$inc":
            for key, delta in fields.items():
                current = _get_path(doc, key)
                if not isinstance(current, (int, float)) or isinstance(current, bool):
                    current = 0
                _set_path(doc, key, current + delta)
        elif operator == "$unset":
            for key in fields:
                _unset_path(doc, key)


# ─── result objects (shape-compatible with pymongo) ───────────────────────

class InsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id
        self.acknowledged = True


class UpdateResult:
    def __init__(self, matched_count, modified_count, upserted_id):
        self.matched_count = matched_count
        self.modified_count = modified_count
        self.upserted_id = upserted_id
        self.acknowledged = True


class DeleteResult:
    def __init__(self, deleted_count):
        self.deleted_count = deleted_count
        self.acknowledged = True


# ─── cursor ───────────────────────────────────────────────────────────────

class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, field, direction=1):
        def sort_key(doc):
            value = _get_path(doc, field)
            if value is None:
                return (0, "")
            if isinstance(value, bool):
                return (1, int(value))
            if isinstance(value, (int, float)):
                return (1, value)
            return (2, str(value))

        self._docs = sorted(self._docs, key=sort_key, reverse=direction < 0)
        return self

    async def to_list(self, length=None):
        return self._docs[:length] if length else list(self._docs)


# ─── collection ───────────────────────────────────────────────────────────

class FileCollection:
    """A single collection persisted as one JSON file."""

    def __init__(self, directory, name):
        self.name = name
        self._path = Path(directory) / f"{name}.json"
        self._lock = asyncio.Lock()
        self._docs = self._load()

    def _load(self):
        if self._path.exists():
            try:
                loaded = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    return loaded
            except (OSError, ValueError) as exc:
                print(f"[store] {self.name}: could not read file ({exc}); starting empty")
        return []

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps(self._docs, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path)  # atomic swap

    async def find_one(self, query=None, projection=None):
        for doc in self._docs:
            if _matches(doc, query):
                return _project(doc, projection)
        return None

    def find(self, query=None, projection=None):
        matched = [_project(d, projection) for d in self._docs if _matches(d, query)]
        return _Cursor(matched)

    async def insert_one(self, document):
        async with self._lock:
            doc = json.loads(json.dumps(document))
            doc.setdefault("_id", uuid.uuid4().hex)
            self._docs.append(doc)
            self._save()
        return InsertResult(doc["_id"])

    async def update_one(self, query, update, upsert=False):
        async with self._lock:
            for doc in self._docs:
                if _matches(doc, query):
                    _apply_update(doc, update)
                    self._save()
                    return UpdateResult(1, 1, None)
            if upsert:
                doc = {}
                # Mongo builds the new doc from equality filter fields + update
                for key, value in (query or {}).items():
                    if key != "_id":
                        _set_path(doc, key, value)
                _apply_update(doc, update)
                doc.setdefault("_id", uuid.uuid4().hex)
                self._docs.append(doc)
                self._save()
                return UpdateResult(0, 0, doc["_id"])
        return UpdateResult(0, 0, None)

    async def delete_one(self, query):
        async with self._lock:
            for index, doc in enumerate(self._docs):
                if _matches(doc, query):
                    del self._docs[index]
                    self._save()
                    return DeleteResult(1)
        return DeleteResult(0)

    async def count_documents(self, query=None):
        return sum(1 for doc in self._docs if _matches(doc, query))

    async def distinct(self, field):
        seen, out = set(), []
        for doc in self._docs:
            value = _get_path(doc, field)
            if value is not None and value not in seen:
                seen.add(value)
                out.append(value)
        return out