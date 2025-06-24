import os
import uuid
from datetime import datetime
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    send_file,
)
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from docx_handler import extract_text_from_docx
from gemini_processor import analyze_essay, get_essay_type

import MySQLdb.cursors

app = Flask(__name__)

# Configuration
app.config["SECRET_KEY"] = "rakib@7254"
app.config["MYSQL_HOST"] = "localhost"
app.config["MYSQL_USER"] = "root"
app.config["MYSQL_PASSWORD"] = "rakib7254"
app.config["MYSQL_DB"] = "essay_revision"
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB max upload
app.config["ALLOWED_EXTENSIONS"] = {"docx"}

# Initialize MySQL
mysql = MySQL(app)

# Ensure upload folder exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]
    )


def get_user_by_username(username):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()
    return user


def get_user_by_id(user_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    return user


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form.get("email")  # Optional, if you want email stored
        password = request.form["password"]

        if get_user_by_username(username):
            flash("Username already exists.", "danger")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)
        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
            (username, email, hashed_password),
        )
        mysql.connection.commit()
        cur.close()
        flash("Registration successful. Please login.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = get_user_by_username(username)
        if user and check_password_hash(
            user[3], password
        ):  # assuming password at index 3
            session["user_id"] = user[0]
            session["username"] = user[1]
            session["role"] = user[4]  # role: user/admin
            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "danger")
        return redirect(url_for("login"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT e.id, e.title, e.essay_type, e.created_at, e.status
        FROM essays e
        WHERE e.user_id = %s
        ORDER BY e.created_at DESC
        """,
        (session["user_id"],),
    )
    essays = cur.fetchall()
    cur.close()

    return render_template("dashboard.html", user=session, essays=essays)


@app.route("/upload", methods=["GET", "POST"])
def upload_essay():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        title = request.form.get("title")
        file = request.files.get("file")

        if not file or file.filename == "":
            flash("No file selected.", "danger")
            return redirect(request.url)

        if not allowed_file(file.filename):
            flash("Invalid file type. Only .docx files allowed.", "danger")
            return redirect(request.url)

        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
        file.save(filepath)

        # Extract text from docx
        essay_text = extract_text_from_docx(filepath)

        # Get essay type (1, 2, 3)
        essay_type = get_essay_type(essay_text)

        # Fetch revision rules from DB for this essay type
        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT rule_name, rule_description FROM revision_rules WHERE essay_type_id = %s",
            (essay_type,),
        )
        rules = cur.fetchall()
        cur.close()

        # Analyze essay and get revisions and revised text
        revisions, revised_text = analyze_essay(essay_text, essay_type, rules)

        # Save essay record in DB
        cur = mysql.connection.cursor()
        cur.execute(
            """
            INSERT INTO essays (user_id, title, content, revised_content, original_file, essay_type, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session["user_id"],
                title,
                essay_text,
                revised_text,
                unique_filename,
                essay_type,
                "completed",
            ),
        )
        mysql.connection.commit()
        essay_id = cur.lastrowid
        cur.close()

        # Save revisions in DB
        cur = mysql.connection.cursor()
        for rev in revisions:
            cur.execute(
                """
                INSERT INTO revisions (essay_id, original_text, revised_text, position, reason)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    essay_id,
                    rev.get("original"),
                    rev.get("revised"),
                    rev.get("position"),
                    rev.get("reason"),
                ),
            )
        mysql.connection.commit()
        cur.close()

        flash("Essay uploaded and processed successfully!", "success")
        return redirect(url_for("view_essay", essay_id=essay_id))

    return render_template("upload.html")


@app.route("/essay/<int:essay_id>")
def view_essay(essay_id):
    if "user_id" not in session:
        flash("Please log in to view essays.", "warning")
        return redirect(url_for("login"))

    # Fetch essay with essay type name
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    query = """
        SELECT
            e.id, e.title, e.content, e.revised_content, e.original_file, e.revised_file,
            e.essay_type, e.status, e.created_at,
            et.name AS essay_type_name
        FROM essays e
        LEFT JOIN essay_types et ON e.essay_type = et.id
        WHERE e.id = %s AND e.user_id = %s
    """
    cur.execute(query, (essay_id, session["user_id"]))
    essay = cur.fetchone()
    cur.close()

    if not essay:
        flash("Essay not found or you do not have permission to view it.", "danger")
        return redirect(url_for("dashboard"))

    # Convert created_at to datetime if string
    if isinstance(essay["created_at"], str):
        from datetime import datetime

        essay["created_at"] = datetime.strptime(
            essay["created_at"], "%Y-%m-%d %H:%M:%S"
        )

    # Fetch revisions for the essay
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute(
        "SELECT id, essay_id, original_text, revised_text, position, reason FROM revisions WHERE essay_id = %s ORDER BY position ASC",
        (essay_id,),
    )
    revisions = cur.fetchall()
    cur.close()

    return render_template("view_essay.html", essay=essay, revisions=revisions)


@app.route("/download/<filename>")
def download_file(filename):
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    if not os.path.exists(filepath):
        flash("File not found.", "danger")
        return redirect(url_for("dashboard"))
    return send_file(filepath, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
