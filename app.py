
import json
import sqlite3

from flask import Flask, abort, flash, redirect, render_template, request, url_for

from config import Config
from database import init_db
from services import knowledge_service as knowledge


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)

    if test_config:
        app.config.update(test_config)

    db_path = app.config.get("DATABASE_PATH")

    try:
        init_db(db_path)
    except sqlite3.Error:
        app.logger.exception("Database initialization failed")
        raise

    def parse_entry(row):
        """Convert stored tag JSON into a list for templates."""
        if row is None:
            return None

        try:
            row["tags_list"] = json.loads(row["tags"])
        except (TypeError, json.JSONDecodeError):
            row["tags_list"] = []

        return row

    @app.route("/")
    def index():
        try:
            entries = knowledge.list_entries(
                search=request.args.get("q", ""),
                category=request.args.get("category", ""),
                db_path=db_path,
            )
            entries = [parse_entry(entry) for entry in entries]
            categories = knowledge.list_categories(db_path)
        except sqlite3.Error:
            app.logger.exception("Could not load knowledge entries")
            abort(500)

        return render_template(
            "index.html",
            entries=entries,
            categories=categories,
            search=request.args.get("q", ""),
            selected_category=request.args.get("category", ""),
        )

    @app.route("/entries/new", methods=["GET", "POST"])
    def new_entry():
        if request.method == "POST":
            try:
                entry_id = knowledge.create_entry(
                    title=request.form.get("title", ""),
                    explanation=request.form.get("explanation", ""),
                    category=request.form.get("category", "General"),
                    tags=request.form.get("tags", ""),
                    db_path=db_path,
                )
                flash("Knowledge entry created.", "success")
                return redirect(url_for("view_entry", entry_id=entry_id))
            except ValueError as error:
                flash(str(error), "error")
            except sqlite3.Error:
                app.logger.exception("Could not create knowledge entry")
                flash("The entry could not be saved. Please try again.", "error")

        return render_template("entry_form.html", entry=None)

    @app.route("/entries/<int:entry_id>")
    def view_entry(entry_id):
        try:
            entry = parse_entry(knowledge.get_entry(entry_id, db_path))

            if entry is None:
                abort(404)

            connections = knowledge.list_connections(entry_id, db_path)
            candidates = knowledge.list_connection_candidates(
                entry_id,
                search=request.args.get("connection_q", ""),
                db_path=db_path,
            )
        except sqlite3.Error:
            app.logger.exception("Could not load knowledge entry or connections")
            abort(500)

        return render_template(
            "entry_detail.html",
            entry=entry,
            connections=connections,
            connection_candidates=candidates,
            connection_search=request.args.get("connection_q", ""),
        )

    @app.route("/entries/<int:entry_id>/edit", methods=["GET", "POST"])
    def edit_entry(entry_id):
        try:
            entry = parse_entry(knowledge.get_entry(entry_id, db_path))
        except sqlite3.Error:
            app.logger.exception("Could not load entry for editing")
            abort(500)

        if entry is None:
            abort(404)

        if request.method == "POST":
            try:
                updated = knowledge.update_entry(
                    entry_id=entry_id,
                    title=request.form.get("title", ""),
                    explanation=request.form.get("explanation", ""),
                    category=request.form.get("category", "General"),
                    tags=request.form.get("tags", ""),
                    db_path=db_path,
                )

                if not updated:
                    abort(404)

                flash("Knowledge entry updated.", "success")
                return redirect(url_for("view_entry", entry_id=entry_id))
            except ValueError as error:
                flash(str(error), "error")
            except sqlite3.Error:
                app.logger.exception("Could not update knowledge entry")
                flash("The entry could not be updated. Please try again.", "error")

        return render_template("entry_form.html", entry=entry)

    @app.route("/entries/<int:entry_id>/connections", methods=["POST"])
    def add_connection(entry_id):
        if not knowledge.get_entry(entry_id, db_path):
            abort(404)

        try:
            related_entry_id = int(request.form.get("related_entry_id", ""))
            connection_id = knowledge.create_knowledge_connection(
                entry_id,
                related_entry_id,
                db_path,
            )

            if connection_id is None:
                flash("These entries are already connected.", "info")
            else:
                flash("Knowledge connection created.", "success")

        except (ValueError, TypeError) as error:
            message = str(error) or "Select a valid entry to connect."
            flash(message, "error")
        except sqlite3.Error:
            app.logger.exception("Could not create knowledge connection")
            flash("The connection could not be created. Please try again.", "error")

        return redirect(url_for("view_entry", entry_id=entry_id))

    @app.route(
        "/entries/<int:entry_id>/connections/<int:connection_id>/delete",
        methods=["POST"],
    )
    def remove_connection(entry_id, connection_id):
        try:
            entry = knowledge.get_entry(entry_id, db_path)
            if entry is None:
                abort(404)

            connections = knowledge.list_connections(entry_id, db_path)
            belongs_to_entry = any(
                item["connection_id"] == connection_id
                for item in connections
            )

            if not belongs_to_entry:
                abort(404)

            deleted = knowledge.delete_knowledge_connection(
                connection_id,
                db_path,
            )

            if not deleted:
                abort(404)

            flash("Knowledge connection removed.", "success")

        except sqlite3.Error:
            app.logger.exception("Could not remove knowledge connection")
            flash("The connection could not be removed. Please try again.", "error")

        return redirect(url_for("view_entry", entry_id=entry_id))

    @app.route("/entries/<int:entry_id>/delete", methods=["POST"])
    def remove_entry(entry_id):
        try:
            deleted = knowledge.delete_entry(entry_id, db_path)
        except sqlite3.Error:
            app.logger.exception("Could not delete knowledge entry")
            flash("The entry could not be deleted. Please try again.", "error")
            return redirect(url_for("index"))

        if not deleted:
            abort(404)

        flash("Knowledge entry deleted.", "success")
        return redirect(url_for("index"))

        @app.route("/graph")
        def knowledge_graph():
            try:
                graph = knowledge.get_knowledge_graph(db_path)
            except sqlite3.Error:
                app.logger.exception("Could not load knowledge graph")
                abort(500)

            return render_template(
                "graph.html",
                graph=graph,
            )

    @app.errorhandler(404)
    def not_found(_error):
        return render_template(
            "error.html",
            heading="Entry not found",
            message="The requested page or knowledge entry does not exist.",
        ), 404

    @app.errorhandler(500)
    def server_error(_error):
        return render_template(
            "error.html",
            heading="Something went wrong",
            message="RecallMap couldn't complete your request. Please try again.",
        ), 500

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=False)