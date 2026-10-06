import json
import sqlite3

from database import get_connection


def list_entries(search="", category="", db_path=None):
    """Return entries matching the optional search and category filters."""
    connection = get_connection(db_path)

    try:
        query = "SELECT * FROM knowledge_entries WHERE 1=1"
        parameters = []

        if search.strip():
            query += " AND (title LIKE ? OR explanation LIKE ? OR tags LIKE ?)"
            term = f"%{search.strip()}%"
            parameters.extend([term, term, term])

        if category.strip():
            query += " AND category = ?"
            parameters.append(category.strip())

        query += " ORDER BY updated_at DESC, id DESC"

        return [
            dict(row)
            for row in connection.execute(query, parameters).fetchall()
        ]
    finally:
        connection.close()


def get_entry(entry_id, db_path=None):
    """Return a single entry, or None when it does not exist."""
    connection = get_connection(db_path)

    try:
        row = connection.execute(
            "SELECT * FROM knowledge_entries WHERE id = ?",
            (entry_id,),
        ).fetchone()

        return dict(row) if row else None
    finally:
        connection.close()


def create_entry(title, explanation="", category="General", tags=None, db_path=None):
    """Validate and create a knowledge entry."""
    title = title.strip() if isinstance(title, str) else ""
    explanation = explanation.strip() if isinstance(explanation, str) else ""
    category = category.strip() if isinstance(category, str) else ""

    if not title:
        raise ValueError("Title is required.")

    if len(title) > 200:
        raise ValueError("Title must be 200 characters or fewer.")

    if len(explanation) > 20000:
        raise ValueError("Explanation must be 20,000 characters or fewer.")

    if not category:
        category = "General"

    if len(category) > 100:
        raise ValueError("Category must be 100 characters or fewer.")

    if isinstance(tags, str):
        tags = tags.split(",")

    cleaned_tags = []
    for tag in tags or []:
        if isinstance(tag, str):
            tag = tag.strip()
            if tag and tag not in cleaned_tags:
                cleaned_tags.append(tag)

    if any(len(tag) > 50 for tag in cleaned_tags):
        raise ValueError("Each tag must be 50 characters or fewer.")

    tags_json = json.dumps(cleaned_tags, ensure_ascii=False)
    connection = get_connection(db_path)

    try:
        cursor = connection.execute(
            """
            INSERT INTO knowledge_entries
                (title, explanation, category, tags)
            VALUES (?, ?, ?, ?)
            """,
            (title, explanation, category, tags_json),
        )
        connection.commit()
        return cursor.lastrowid
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()


def update_entry(entry_id, title, explanation="", category="General", tags=None,
                 db_path=None):
    """Update an existing entry. Return False if it does not exist."""
    if not get_entry(entry_id, db_path):
        return False

    title = title.strip() if isinstance(title, str) else ""
    explanation = explanation.strip() if isinstance(explanation, str) else ""
    category = category.strip() if isinstance(category, str) else ""

    if not title:
        raise ValueError("Title is required.")
    if len(title) > 200:
        raise ValueError("Title must be 200 characters or fewer.")
    if len(explanation) > 20000:
        raise ValueError("Explanation must be 20,000 characters or fewer.")
    if not category:
        category = "General"
    if len(category) > 100:
        raise ValueError("Category must be 100 characters or fewer.")

    if isinstance(tags, str):
        tags = tags.split(",")

    cleaned_tags = []
    for tag in tags or []:
        if isinstance(tag, str):
            tag = tag.strip()
            if tag and tag not in cleaned_tags:
                cleaned_tags.append(tag)

    if any(len(tag) > 50 for tag in cleaned_tags):
        raise ValueError("Each tag must be 50 characters or fewer.")

    connection = get_connection(db_path)

    try:
        cursor = connection.execute(
            """
            UPDATE knowledge_entries
            SET title = ?, explanation = ?, category = ?, tags = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ?
            """,
            (
                title,
                explanation,
                category,
                json.dumps(cleaned_tags, ensure_ascii=False),
                entry_id,
            ),
        )
        connection.commit()
        return cursor.rowcount > 0
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()


def delete_entry(entry_id, db_path=None):
    """Delete an entry. Return False if it does not exist."""
    connection = get_connection(db_path)

    try:
        cursor = connection.execute(
            "DELETE FROM knowledge_entries WHERE id = ?",
            (entry_id,),
        )
        connection.commit()
        return cursor.rowcount > 0
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()


def list_categories(db_path=None):
    """Return distinct categories used by existing entries."""
    connection = get_connection(db_path)

    try:
        rows = connection.execute("""
            SELECT DISTINCT category
            FROM knowledge_entries
            ORDER BY category COLLATE NOCASE
        """).fetchall()
        return [row["category"] for row in rows]
    finally:
        connection.close()