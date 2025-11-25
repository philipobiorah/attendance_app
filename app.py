import io
import uuid
from datetime import datetime, timedelta

from flask import (
    Flask, request, redirect, url_for,
    render_template, send_file, flash
)
from flask_sqlalchemy import SQLAlchemy
import qrcode

app = Flask(__name__)
app.secret_key = "change-me"  # replace with something random in real use

# SQLite database
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///attendance.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


# ---------- MODELS ----------

class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False)
    course_name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("session.id"), nullable=False)
    student_id = db.Column(db.String(50), nullable=False)
    marked_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("session_id", "student_id", name="uq_session_student"),
    )


with app.app_context():
    db.create_all()


# ---------- ROUTES FOR TEACHER ----------

@app.route("/", methods=["GET", "POST"])
def create_session():
    """
    Teacher creates a new attendance session.
    """
    if request.method == "POST":
        course_name = request.form.get("course_name", "Untitled class")
        duration_minutes = int(request.form.get("duration_minutes", 15))

        code = str(uuid.uuid4())
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=duration_minutes)

        session = Session(
            code=code,
            course_name=course_name,
            created_at=now,
            expires_at=expires_at,
        )
        db.session.add(session)
        db.session.commit()

        return redirect(url_for("show_session", code=code))

    return render_template("create_session.html")


@app.route("/session/<code>")
def show_session(code):
    """
    Show QR code for the session and some info.
    """
    session = Session.query.filter_by(code=code).first_or_404()
    return render_template("success.html", session=session)


@app.route("/session/<code>/qr")
def session_qr(code):
    """
    Generate QR code image that encodes the attendance URL.
    """
    session = Session.query.filter_by(code=code).first_or_404()
    attend_url = url_for("attend", code=session.code, _external=True)

    img = qrcode.make(attend_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return send_file(buf, mimetype="image/png")


# ---------- ROUTES FOR STUDENTS ----------

@app.route("/attend/<code>", methods=["GET", "POST"])
def attend(code):
    """
    Student scans QR -> lands here -> enters student ID -> attendance recorded.
    """
    session = Session.query.filter_by(code=code).first_or_404()

    # Check if the session has expired
    if datetime.utcnow() > session.expires_at:
        return "This attendance link has expired.", 410

    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()

        if not student_id:
            flash("Please enter your student ID.")
            return redirect(request.url)

        # Check if already marked for this session
        existing = Attendance.query.filter_by(
            session_id=session.id,
            student_id=student_id
        ).first()

        if existing:
            return "Your attendance is already recorded for this session."

        record = Attendance(session_id=session.id, student_id=student_id)
        db.session.add(record)
        db.session.commit()

        return "Attendance recorded successfully. You can close this page."

    return render_template("attend.html", session=session)


@app.route("/session/<code>/attendance")
def view_attendance(code):
    """
    View attendance list for a specific session.
    """
    session = Session.query.filter_by(code=code).first_or_404()
    records = Attendance.query.filter_by(session_id=session.id).order_by(Attendance.marked_at).all()
    return render_template("attendance_list.html", session=session, records=records)


# For AWS Elastic Beanstalk
application = app

if __name__ == "__main__":
    app.run(debug=True)
