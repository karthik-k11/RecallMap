
import json
import sqlite3

from database import get_connection


def list_entries(search="", category="", db_path=None):
    """Return entries matching optional search and category filters."""
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
    """Return one entry or None."""
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT * FROM knowledge_entries WHERE id = ?",
            (entry_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def _validate_entry(title, explanation, category, tags):
    """Validate and normalize knowledge entry fields."""
    title = title.strip() if isinstance(title, str) else ""
    explanation = explanation.strip() if isinstance(explanation, str) else ""
    category = category.strip() if isinstance(category, str) else ""

    if not title:
        raise ValueError("Title is required.")
    if len(title) > 200:
        raise ValueError("Title must be 200 characters or fewer.")
    if len(explanation) > 20000:
        raise ValueError("Explanation must be 20,000 characters or fewer.")

    category = category or "General"
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

    return title, explanation, category, json.dumps(
        cleaned_tags, ensure_ascii=False
    )


def create_entry(
    title, explanation="", category="General", tags=None, db_path=None
):
    """Validate and create a knowledge entry."""
    title, explanation, category, tags_json = _validate_entry(
        title, explanation, category, tags
    )
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


def update_entry(
    entry_id, title, explanation="", category="General",
    tags=None, db_path=None
):
    """Update an entry. Return False if it does not exist."""
    if not get_entry(entry_id, db_path):
        return False

    title, explanation, category, tags_json = _validate_entry(
        title, explanation, category, tags
    )
    connection = get_connection(db_path)

    try:
        cursor = connection.execute(
            """
            UPDATE knowledge_entries
            SET title = ?, explanation = ?, category = ?, tags = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ?
            """,
            (title, explanation, category, tags_json, entry_id),
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
    """Return distinct categories."""
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


def create_knowledge_connection(entry_id, related_entry_id, db_path=None):
    """Connect two entries bidirectionally without duplicates."""
    if entry_id == related_entry_id:
        raise ValueError("An entry cannot be connected to itself.")

    first_id, second_id = sorted((entry_id, related_entry_id))
    connection = get_connection(db_path)

    try:
        existing = connection.execute(
            """
            SELECT id FROM knowledge_entries
            WHERE id IN (?, ?)
            """,
            (first_id, second_id),
        ).fetchall()

        if len(existing) != 2:
            raise ValueError("Both knowledge entries must exist.")

        cursor = connection.execute(
            """
            INSERT INTO knowledge_connections
                (entry_id, related_entry_id)
            VALUES (?, ?)
            ON CONFLICT(entry_id, related_entry_id) DO NOTHING
            """,
            (first_id, second_id),
        )
        connection.commit()
        return cursor.lastrowid if cursor.rowcount else None

    except (sqlite3.Error, ValueError):
        connection.rollback()
        raise
    finally:
        connection.close()


def list_connections(entry_id, db_path=None):
    """Return all entries connected to this entry."""
    connection = get_connection(db_path)
    try:
        rows = connection.execute(
            """
            SELECT kc.id AS connection_id, ke.*
            FROM knowledge_connections AS kc
            JOIN knowledge_entries AS ke
              ON ke.id = CASE
                  WHEN kc.entry_id = ? THEN kc.related_entry_id
                  ELSE kc.entry_id
              END
            WHERE kc.entry_id = ? OR kc.related_entry_id = ?
            ORDER BY ke.title COLLATE NOCASE
            """,
            (entry_id, entry_id, entry_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def list_connection_candidates(entry_id, search="", db_path=None):
    """Return unconnected entries available to link."""
    connection = get_connection(db_path)
    try:
        query = """
            SELECT ke.*
            FROM knowledge_entries AS ke
            WHERE ke.id != ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM knowledge_connections AS kc
                  WHERE
                    (kc.entry_id = ? AND kc.related_entry_id = ke.id)
                    OR
                    (kc.related_entry_id = ? AND kc.entry_id = ke.id)
              )
        """
        parameters = [entry_id, entry_id, entry_id]

        if search.strip():
            query += """
                AND (
                    ke.title LIKE ?
                    OR ke.explanation LIKE ?
                    OR ke.tags LIKE ?
                )
            """
            term = f"%{search.strip()}%"
            parameters.extend([term, term, term])

        query += " ORDER BY ke.title COLLATE NOCASE"
        return [
            dict(row)
            for row in connection.execute(query, parameters).fetchall()
        ]
    finally:
        connection.close()


def delete_knowledge_connection(connection_id, db_path=None):
    """Remove a link without deleting either entry."""
    connection = get_connection(db_path)
    try:
        cursor = connection.execute(
            "DELETE FROM knowledge_connections WHERE id = ?",
            (connection_id,),
        )
        connection.commit()
        return cursor.rowcount > 0
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()

def get_knowledge_graph(db_path=None):
    """Return all entries and their connections for graph visualization."""
    connection = get_connection(db_path)

    try:
        entries = connection.execute(
            """
            SELECT id, title, category
            FROM knowledge_entries
            ORDER BY title COLLATE NOCASE
            """
        ).fetchall()

        connections = connection.execute(
            """
            SELECT entry_id, related_entry_id
            FROM knowledge_connections
            ORDER BY id
            """
        ).fetchall()

        return {
            "nodes": [dict(entry) for entry in entries],
            "edges": [dict(item) for item in connections],
        }
    finally:
        connection.close()