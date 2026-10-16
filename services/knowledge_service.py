
import json
import sqlite3

from database import get_connection


def _normalize_tags(tags):
    """Convert comma-separated text or a list into unique tags."""
    if tags is None:
        return []

    if isinstance(tags, str):
        tags = tags.split(",")

    if not isinstance(tags, (list, tuple)):
        raise ValueError("Tags must be provided as text or a list.")

    result = []
    seen = set()

    for tag in tags:
        if not isinstance(tag, str):
            raise ValueError("Each tag must be text.")

        tag = tag.strip()

        if tag and tag.casefold() not in seen:
            result.append(tag)
            seen.add(tag.casefold())

    return result


def _validate_entry(title, explanation, category, tags):
    """Validate and normalize knowledge-entry fields."""
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Title is required.")

    title = title.strip()

    if len(title) > 200:
        raise ValueError("Title must not exceed 200 characters.")

    if explanation is None:
        explanation = ""

    if not isinstance(explanation, str):
        raise ValueError("Explanation must be text.")

    if category is None:
        category = "General"

    if not isinstance(category, str):
        raise ValueError("Category must be text.")

    category = category.strip() or "General"

    if len(category) > 100:
        raise ValueError("Category must not exceed 100 characters.")

    return title, explanation, category, _normalize_tags(tags)


def list_entries(search="", category="", db_path=None):
    """List entries, optionally filtering by search text and category."""
    connection = get_connection(db_path)

    try:
        query = """
            SELECT *
            FROM knowledge_entries
            WHERE 1 = 1
        """
        parameters = []

        if search and search.strip():
            query += """
                AND (
                    title LIKE ?
                    OR explanation LIKE ?
                    OR tags LIKE ?
                )
            """
            term = f"%{search.strip()}%"
            parameters.extend([term, term, term])

        if category and category.strip():
            query += " AND category = ?"
            parameters.append(category.strip())

        query += " ORDER BY updated_at DESC, id DESC"

        return connection.execute(
            query,
            parameters,
        ).fetchall()
    finally:
        connection.close()


def get_entry(entry_id, db_path=None):
    """Retrieve a single entry by ID."""
    connection = get_connection(db_path)

    try:
        return connection.execute(
            "SELECT * FROM knowledge_entries WHERE id = ?",
            (entry_id,),
        ).fetchone()
    finally:
        connection.close()


def create_entry(
    title,
    explanation="",
    category="General",
    tags=None,
    db_path=None,
):
    """Create a knowledge entry and return its ID."""
    title, explanation, category, tags = _validate_entry(
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
            (
                title,
                explanation,
                category,
                json.dumps(tags, ensure_ascii=False),
            ),
        )
        connection.commit()
        return cursor.lastrowid
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()


def update_entry(
    entry_id,
    title,
    explanation="",
    category="General",
    tags=None,
    db_path=None,
):
    """Update an existing entry; return whether it existed."""
    title, explanation, category, tags = _validate_entry(
        title, explanation, category, tags
    )

    connection = get_connection(db_path)

    try:
        cursor = connection.execute(
            """
            UPDATE knowledge_entries
            SET title = ?,
                explanation = ?,
                category = ?,
                tags = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ?
            """,
            (
                title,
                explanation,
                category,
                json.dumps(tags, ensure_ascii=False),
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
    """Delete an entry and its dependent connections."""
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
    """Return distinct non-empty categories."""
    connection = get_connection(db_path)

    try:
        rows = connection.execute(
            """
            SELECT DISTINCT category
            FROM knowledge_entries
            WHERE trim(category) != ''
            ORDER BY category COLLATE NOCASE
            """
        ).fetchall()

        return [row["category"] for row in rows]
    finally:
        connection.close()


# Knowledge Connections


def create_knowledge_connection(entry_id, related_entry_id, db_path=None):
    """Create a bidirectional connection between two different entries."""
    if entry_id == related_entry_id:
        raise ValueError("An entry cannot be connected to itself.")

    connection = get_connection(db_path)

    try:
        existing_entries = connection.execute(
            """
            SELECT id
            FROM knowledge_entries
            WHERE id IN (?, ?)
            """,
            (entry_id, related_entry_id),
        ).fetchall()

        if len(existing_entries) != 2:
            raise ValueError("Both knowledge entries must exist.")

        first_id, second_id = sorted(
            (entry_id, related_entry_id)
        )

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

        if cursor.rowcount == 0:
            return None

        return cursor.lastrowid
    except (sqlite3.Error, ValueError):
        connection.rollback()
        raise
    finally:
        connection.close()


def list_connections(entry_id, db_path=None):
    """List all entries connected to the specified entry."""
    connection = get_connection(db_path)

    try:
        return connection.execute(
            """
            SELECT
                kc.id AS connection_id,
                e.id,
                e.title,
                e.category
            FROM knowledge_connections kc
            JOIN knowledge_entries e
              ON e.id = CASE
                    WHEN kc.entry_id = ?
                    THEN kc.related_entry_id
                    ELSE kc.entry_id
                 END
            WHERE kc.entry_id = ? OR kc.related_entry_id = ?
            ORDER BY e.title COLLATE NOCASE
            """,
            (entry_id, entry_id, entry_id),
        ).fetchall()
    finally:
        connection.close()


def list_connection_candidates(entry_id, search="", db_path=None):
    """List entries that can be connected to the specified entry."""
    connection = get_connection(db_path)

    try:
        query = """
            SELECT e.id, e.title, e.category
            FROM knowledge_entries e
            WHERE e.id != ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM knowledge_connections kc
                  WHERE (
                      kc.entry_id = ?
                      AND kc.related_entry_id = e.id
                  )
                  OR (
                      kc.related_entry_id = ?
                      AND kc.entry_id = e.id
                  )
              )
        """

        parameters = [entry_id, entry_id, entry_id]

        if search and search.strip():
            query += """
                AND (
                    e.title LIKE ?
                    OR e.category LIKE ?
                )
            """
            term = f"%{search.strip()}%"
            parameters.extend([term, term])

        query += " ORDER BY e.title COLLATE NOCASE"

        return connection.execute(
            query,
            parameters,
        ).fetchall()
    finally:
        connection.close()


def delete_knowledge_connection(connection_id, db_path=None):
    """Delete a connection without deleting either entry."""
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


# Knowledge Graph


def get_knowledge_graph(db_path=None):
    """Return graph nodes and edges for visualization."""
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


# Knowledge Insights


def get_knowledge_insights(db_path=None):
    """Return library statistics and relationship insights."""
    connection = get_connection(db_path)

    try:
        total_entries = connection.execute(
            "SELECT COUNT(*) FROM knowledge_entries"
        ).fetchone()[0]

        total_connections = connection.execute(
            "SELECT COUNT(*) FROM knowledge_connections"
        ).fetchone()[0]

        category_rows = connection.execute(
            """
            SELECT category, COUNT(*) AS entry_count
            FROM knowledge_entries
            GROUP BY category
            ORDER BY entry_count DESC, category COLLATE NOCASE
            """
        ).fetchall()

        connected_rows = connection.execute(
            """
            SELECT
                e.id,
                e.title,
                e.category,
                COUNT(kc.id) AS connection_count
            FROM knowledge_entries e
            LEFT JOIN knowledge_connections kc
              ON e.id = kc.entry_id
              OR e.id = kc.related_entry_id
            GROUP BY e.id, e.title, e.category
            ORDER BY connection_count DESC, e.title COLLATE NOCASE
            """
        ).fetchall()

        most_connected = [
            dict(row)
            for row in connected_rows
            if row["connection_count"] > 0
        ]

        isolated_entries = [
            dict(row)
            for row in connected_rows
            if row["connection_count"] == 0
        ]

        average_connections = (
            (total_connections * 2) / total_entries
            if total_entries
            else 0
        )

        return {
            "total_entries": total_entries,
            "total_connections": total_connections,
            "average_connections": round(average_connections, 2),
            "categories": [dict(row) for row in category_rows],
            "most_connected": most_connected,
            "isolated_entries": isolated_entries,
        }
    finally:
        connection.close()


# JSON Backup and Restore


def export_knowledge_data(db_path=None):
    """Export entries and connections as JSON-ready data."""
    connection = get_connection(db_path)

    try:
        entries = connection.execute(
            """
            SELECT id, title, explanation, category, tags,
                   created_at, updated_at
            FROM knowledge_entries
            ORDER BY id
            """
        ).fetchall()

        connections = connection.execute(
            """
            SELECT entry_id, related_entry_id
            FROM knowledge_connections
            ORDER BY id
            """
        ).fetchall()

        exported_entries = []

        for entry in entries:
            item = dict(entry)

            try:
                item["tags"] = json.loads(item["tags"])
            except (TypeError, json.JSONDecodeError):
                item["tags"] = []

            exported_entries.append(item)

        return {
            "format_version": 1,
            "entries": exported_entries,
            "connections": [
                {
                    "entry_id": item["entry_id"],
                    "related_entry_id": item["related_entry_id"],
                }
                for item in connections
            ],
        }
    finally:
        connection.close()


def import_knowledge_data(data, db_path=None):
    """
    Import a RecallMap JSON backup.

    Imported entries receive new IDs so existing entries are not overwritten.
    Connections are recreated using the new IDs.
    Returns counts of imported entries and connections.
    """
    if not isinstance(data, dict):
        raise ValueError("Backup must be a JSON object.")

    if data.get("format_version") != 1:
        raise ValueError("Unsupported or missing backup format version.")

    entries = data.get("entries")
    connections_data = data.get("connections")

    if not isinstance(entries, list) or not isinstance(connections_data, list):
        raise ValueError("Backup must contain entries and connections lists.")

    normalized_entries = []
    old_ids = set()

    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("Each entry must be a JSON object.")

        old_id = item.get("id")

        if not isinstance(old_id, int) or isinstance(old_id, bool):
            raise ValueError("Each entry must have an integer ID.")

        if old_id in old_ids:
            raise ValueError("Backup contains duplicate entry IDs.")

        old_ids.add(old_id)

        title, explanation, category, tags = _validate_entry(
            item.get("title"),
            item.get("explanation", ""),
            item.get("category", "General"),
            item.get("tags", []),
        )

        normalized_entries.append({
            "old_id": old_id,
            "title": title,
            "explanation": explanation,
            "category": category,
            "tags": tags,
        })

    normalized_connections = set()

    for item in connections_data:
        if not isinstance(item, dict):
            raise ValueError("Each connection must be a JSON object.")

        first_id = item.get("entry_id")
        second_id = item.get("related_entry_id")

        if (
            not isinstance(first_id, int)
            or isinstance(first_id, bool)
            or not isinstance(second_id, int)
            or isinstance(second_id, bool)
        ):
            raise ValueError("Connection IDs must be integers.")

        if first_id == second_id:
            raise ValueError("Self-connections are not allowed.")

        if first_id not in old_ids or second_id not in old_ids:
            raise ValueError("Connection references a missing backup entry.")

        normalized_connections.add(tuple(sorted((first_id, second_id))))

    connection = get_connection(db_path)

    try:
        connection.execute("BEGIN")

        id_mapping = {}

        for item in normalized_entries:
            cursor = connection.execute(
                """
                INSERT INTO knowledge_entries
                    (title, explanation, category, tags)
                VALUES (?, ?, ?, ?)
                """,
                (
                    item["title"],
                    item["explanation"],
                    item["category"],
                    json.dumps(item["tags"], ensure_ascii=False),
                ),
            )

            id_mapping[item["old_id"]] = cursor.lastrowid

        imported_connections = 0

        for first_id, second_id in sorted(normalized_connections):
            new_first_id = id_mapping[first_id]
            new_second_id = id_mapping[second_id]

            cursor = connection.execute(
                """
                INSERT INTO knowledge_connections
                    (entry_id, related_entry_id)
                VALUES (?, ?)
                ON CONFLICT(entry_id, related_entry_id) DO NOTHING
                """,
                tuple(sorted((new_first_id, new_second_id))),
            )

            imported_connections += cursor.rowcount

        connection.commit()

        return {
            "entries_imported": len(normalized_entries),
            "connections_imported": imported_connections,
        }

    except (sqlite3.Error, ValueError):
        connection.rollback()
        raise
    finally:
        connection.close()