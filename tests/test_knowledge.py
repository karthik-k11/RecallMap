
import json

import pytest

from app import create_app
from database import init_db
from services import knowledge_service as knowledge


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test_recallmap.db"
    init_db(path)
    return path


@pytest.fixture
def client(db_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-key",
        "DATABASE_PATH": db_path,
    })
    return app.test_client()


def test_create_entry(db_path):
    entry_id = knowledge.create_entry(
        "Python decorators",
        "Decorators wrap functions.",
        "Python",
        "functions, decorators, functions",
        db_path,
    )

    entry = knowledge.get_entry(entry_id, db_path)

    assert entry["title"] == "Python decorators"
    assert entry["category"] == "Python"
    assert json.loads(entry["tags"]) == ["functions", "decorators"]
    assert entry["created_at"]
    assert entry["updated_at"]


def test_title_is_required(db_path):
    with pytest.raises(ValueError, match="Title is required"):
        knowledge.create_entry("   ", db_path=db_path)


def test_title_length_validation(db_path):
    with pytest.raises(ValueError, match="200 characters"):
        knowledge.create_entry("x" * 201, db_path=db_path)


def test_edit_entry(db_path):
    entry_id = knowledge.create_entry("Original", db_path=db_path)

    updated = knowledge.update_entry(
        entry_id, "Updated", "New explanation", "Python", ["testing"],
        db_path,
    )

    entry = knowledge.get_entry(entry_id, db_path)

    assert updated is True
    assert entry["title"] == "Updated"
    assert entry["explanation"] == "New explanation"
    assert entry["category"] == "Python"


def test_delete_entry(db_path):
    entry_id = knowledge.create_entry("Temporary", db_path=db_path)

    assert knowledge.delete_entry(entry_id, db_path) is True
    assert knowledge.get_entry(entry_id, db_path) is None
    assert knowledge.delete_entry(entry_id, db_path) is False


def test_search_and_category_filter(db_path):
    knowledge.create_entry(
        "Python functions", "Reusable code", "Python", db_path=db_path
    )
    knowledge.create_entry(
        "SQL joins", "Combine database tables", "SQL", db_path=db_path
    )

    results = knowledge.list_entries(search="Python", db_path=db_path)
    assert len(results) == 1
    assert results[0]["title"] == "Python functions"

    results = knowledge.list_entries(category="SQL", db_path=db_path)
    assert len(results) == 1
    assert results[0]["title"] == "SQL joins"


def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Knowledge library" in response.data


def test_create_entry_route(client):
    response = client.post(
        "/entries/new",
        data={
            "title": "Flask basics",
            "explanation": "Flask handles HTTP requests.",
            "category": "Python",
            "tags": "web, backend",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Flask basics" in response.data
    assert b"Knowledge entry created." in response.data


def test_invalid_entry_route(client):
    response = client.post(
        "/entries/new",
        data={"title": "   "},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Title is required." in response.data


def test_unknown_entry_returns_404(client):
    response = client.get("/entries/99999")
    assert response.status_code == 404


def test_delete_route(client, db_path):
    entry_id = knowledge.create_entry("Delete me", db_path=db_path)

    response = client.post(
        f"/entries/{entry_id}/delete",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert knowledge.get_entry(entry_id, db_path) is None


# Knowledge Connections tests

def test_create_knowledge_connection(db_path):
    first_id = knowledge.create_entry("Python Lists", db_path=db_path)
    second_id = knowledge.create_entry("List Comprehension", db_path=db_path)

    knowledge.create_knowledge_connection(first_id, second_id, db_path)

    first_connections = knowledge.list_connections(first_id, db_path)
    second_connections = knowledge.list_connections(second_id, db_path)

    assert len(first_connections) == 1
    assert first_connections[0]["id"] == second_id

    assert len(second_connections) == 1
    assert second_connections[0]["id"] == first_id


def test_duplicate_connection_is_prevented(db_path):
    first_id = knowledge.create_entry("Entry A", db_path=db_path)
    second_id = knowledge.create_entry("Entry B", db_path=db_path)

    knowledge.create_knowledge_connection(first_id, second_id, db_path)
    knowledge.create_knowledge_connection(second_id, first_id, db_path)

    assert len(knowledge.list_connections(first_id, db_path)) == 1
    assert len(knowledge.list_connections(second_id, db_path)) == 1


def test_self_connection_is_rejected(db_path):
    entry_id = knowledge.create_entry("Standalone entry", db_path=db_path)

    with pytest.raises(ValueError):
        knowledge.create_knowledge_connection(entry_id, entry_id, db_path)


def test_connection_to_missing_entry_is_rejected(db_path):
    entry_id = knowledge.create_entry("Existing entry", db_path=db_path)

    with pytest.raises(ValueError):
        knowledge.create_knowledge_connection(entry_id, 99999, db_path)


def test_delete_connection_preserves_entries(db_path):
    first_id = knowledge.create_entry("Entry A", db_path=db_path)
    second_id = knowledge.create_entry("Entry B", db_path=db_path)

    connection_id = knowledge.create_knowledge_connection(
        first_id, second_id, db_path
    )

    assert connection_id is not None
    assert knowledge.delete_knowledge_connection(connection_id, db_path) is True

    assert knowledge.list_connections(first_id, db_path) == []
    assert knowledge.list_connections(second_id, db_path) == []
    assert knowledge.get_entry(first_id, db_path) is not None
    assert knowledge.get_entry(second_id, db_path) is not None


def test_deleting_entry_removes_its_connections(db_path):
    first_id = knowledge.create_entry("Entry A", db_path=db_path)
    second_id = knowledge.create_entry("Entry B", db_path=db_path)

    knowledge.create_knowledge_connection(first_id, second_id, db_path)

    assert knowledge.delete_entry(first_id, db_path) is True
    assert knowledge.get_entry(second_id, db_path) is not None
    assert knowledge.list_connections(second_id, db_path) == []