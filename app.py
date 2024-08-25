import validators
import humanize

from cs50 import SQL
from datetime import datetime, timezone
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import login_required, apology

# Configure application
app = Flask(__name__)

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///postee.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@login_required
def user():
    user_id = session["user_id"]

    user_profile = db.execute(
        "SELECT name, username, email FROM users WHERE id = ?", user_id
    )[0]

    # Get the list of follower IDs for the current user
    followers = db.execute(
        "SELECT follower_id FROM followers WHERE user_id = ?", user_id
    )
    follower_ids = [f["follower_id"] for f in followers]

    who_to_follow = db.execute(
        """
        SELECT id, name, username FROM users
        WHERE id != ?
        ORDER BY (
            SELECT COUNT(*) FROM followers
            WHERE user_id = users.id
        ) DESC;
        """, user_id,
    )

    return user_profile, who_to_follow, follower_ids


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    user_id = session["user_id"]

    if request.method == "POST":
        follow_user_id = request.form.get("follow_user_id")
        action = request.form.get("action")

        if follow_user_id:
            if action == "follow":
                # Add the follower record to the database
                db.execute(
                    "INSERT INTO followers (user_id, follower_id) VALUES (?, ?)",
                    user_id, follow_user_id
                )
            elif action == "unfollow":
                # Remove the follower record from the database
                db.execute(
                    "DELETE FROM followers WHERE user_id = ? AND follower_id = ?",
                    user_id, follow_user_id
                )

        # Redirect to the index page after updating follow status
        return redirect(url_for("index"))

    user_profile, who_to_follow, follower_ids = user()

    # Fetch posts excluding the user's own posts, prioritize followed users, and order by most recent
    posts = db.execute(
        """
        SELECT posts.post, posts.timing, users.name, users.username,
            CASE 
                WHEN posts.user_id IN (SELECT follower_id FROM followers WHERE user_id = ?) THEN 1
                ELSE 2
            END AS priority
        FROM posts
        JOIN users ON posts.user_id = users.id
        WHERE posts.user_id != ?
        ORDER BY priority, posts.timing DESC
        """, user_id, user_id
    )



    # Format the timing of each post
    for post in posts:
        post_time = datetime.strptime(post["timing"], "%Y-%m-%d %H:%M:%S")
        post_time = post_time.replace(tzinfo=timezone.utc)  # Make it timezone-aware
        post["timing"] = humanize.naturaltime(datetime.now(timezone.utc) - post_time)

    return render_template(
        "index.html",
        who_to_follow=who_to_follow,
        userprofile=user_profile,
        follower_ids=follower_ids,
        posts=posts,
    )


@app.route("/post", methods=["GET", "POST"])
@login_required
def post():
    user_id = session["user_id"]

    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "delete":
            post_id = request.form.get("post_id")

            # Ensure the post ID is provided
            if not post_id:
                return apology("No post selected for deletion")

            # Delete the post from the database
            try:
                db.execute("DELETE FROM posts WHERE id = ? AND user_id = ?", post_id, user_id)
            except Exception as e:
                return apology("Error deleting your post: " + str(e))

            # Redirect to the home page after deleting
            return redirect(url_for("post"))

        post_content = request.form.get("post")

        # Ensure the post is not empty
        if not post_content:
            return apology("Post content cannot be empty")

        # Insert the post into the database
        try:
            db.execute(
                "INSERT INTO posts (user_id, post, timing) VALUES (?, ?, ?)",
                user_id,
                post_content,
                datetime.now(timezone.utc),
            )
        except Exception as e:
            return apology("Error saving your post: " + str(e))

        # Redirect to the home page after posting
        return redirect(url_for("post"))

    user_profile, who_to_follow, follower_ids = user()

    # Fetch posts from followers, ordered by most recent
    posts = db.execute(
        """
        SELECT posts.id, posts.post, posts.timing FROM posts
        JOIN users ON posts.user_id = users.id
        WHERE posts.user_id = ?
        ORDER BY posts.timing DESC
        """, user_id
    )

    # Format the timing of each post
    for post in posts:
        post_time = datetime.strptime(post["timing"], "%Y-%m-%d %H:%M:%S")
        post_time = post_time.replace(tzinfo=timezone.utc)  # Make it timezone-aware
        post["timing"] = humanize.naturaltime(datetime.now(timezone.utc) - post_time)

    return render_template(
        "post.html",
        who_to_follow=who_to_follow,
        userprofile=user_profile,
        follower_ids=follower_ids,
        posts=posts,
    )


@app.route("/edit-profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    user_id = session["user_id"]

    if request.method == "POST":
        name = request.form.get("name")
        username = request.form.get("username")
        email = request.form.get("email")

        if not name:
            return apology("missing full name")

        if not username:
            return apology("missing username")

        if not email:
            return apology("missing email")

        if not validators.email(email):
            return apology("invalid email")

        # Update the user's profile information in the database
        try:
            db.execute(
                "UPDATE users SET name = ?, username = ?, email = ? WHERE id = ?",
                name,
                username,
                email,
                user_id,
            )
        except ValueError:
            return apology("username or email already taken")

        # Redirect to the profile or home page after saving changes
        return redirect("/")

    else:
        user_profile, who_to_follow, follower_ids = user()
        return render_template(
            "edit.html",
            who_to_follow=who_to_follow,
            userprofile=user_profile,
            follower_ids=follower_ids,
        )


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":
        name = request.form.get("name")
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not name:
            return apology("missing full name")

        elif not email:
            return apology("missing email")

        elif not validators.email(email):
            return apology("invalid email")

        elif not username:
            return apology("missing username")

        elif not password:
            return apology("missing password")

        elif not confirmation or password != confirmation:
            return apology("password don't match")

        try:
            password_hash = generate_password_hash(password)
            db.execute(
                "INSERT INTO users (name, username, email, hash) VALUES(?, ?, ?, ?)",
                name,
                username,
                email,
                password_hash,
            )
        except ValueError:
            return apology("username or email taken")

        rows = db.execute("SELECT * FROM users WHERE username = ?", username)

        session["user_id"] = rows[0]["id"]

        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        login = request.form.get("login")
        password = request.form.get("password")

        if not login:
            return apology("must provide username or email", 403)

        elif not password:
            return apology("must provide password", 403)

        # Query database for username
        if validators.email(login):
            rows = db.execute("SELECT * FROM users WHERE email = ?", login)
        else:
            rows = db.execute("SELECT * FROM users WHERE username = ?", login)

        # Ensure username or email exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], password):
            return apology("invalid username or email and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        return redirect("/")

    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/login")
