from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from flask_bcrypt import Bcrypt
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from bson import ObjectId
import logging
from flask import request
import os
import uuid



app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key")

app.config["MONGO_URI"] = "mongodb://localhost:27017/Peer_Tutoring"
mongo = PyMongo(app)
users_collection = mongo.db.users
db = mongo.db
availability_collection = db["availability"]
bookings_collection = db["bookings"]
sessions_collection = bookings_collection  # Assuming sessions are stored in bookings_collection   
students_collection = db["students"]
tutors_collection = db["tutors"]
available_sessions_collection = db["available_sessions"]


bcrypt = Bcrypt(app)

# Flask-Mail Configuration
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER")

mail = Mail(app)
serializer = URLSafeTimedSerializer(app.secret_key)

# ✅ List of IT course units
units = [
    "Introduction to Programming",
    "Object-Oriented Programming",
    "Web Development",
    "Database Management Systems",
    "Software Engineering Principles"
]

# ✅ Home Route
@app.route("/")
def home():
    user_email = None
    if "user_id" in session:
        user = users_collection.find_one({"_id": ObjectId(session["user_id"])})
        if user:
            user_email = user.get("email")

    return render_template("index.html", user_email=user_email)

# ✅ Register Route
@app.route("/register", methods=["GET", "POST"])
def register():
    unit_mapping = {
        "Introduction to Programming": "Introduction to Programming",
        "Object-Oriented Programming (OOP)": "Object-Oriented Programming",
        "Web Development (HTML, CSS, JavaScript, Flask)": "Web Development",
        "Database Management Systems (SQL & NoSQL)": "Database Management Systems",
        "Software Engineering Principles": "Software Engineering Principles"
    }

    if request.method == "POST":
        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role")
        units_selected = request.form.getlist("units") if role == "tutor" else []

        # Convert unit names to match database format
        units_selected = [unit_mapping.get(unit, unit) for unit in units_selected]

        existing_user = users_collection.find_one({"email": email})
        if existing_user:
            flash("Email already registered.", "danger")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        user = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "password": hashed_password,
            "role": role,
            "units": units_selected
        }

        users_collection.insert_one(user)
        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

# ✅ Login Route
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email").strip().lower()
        password = request.form.get("password")

        user = users_collection.find_one({"email": email})

        if user:
            stored_password = user["password"]
            print("Stored password:", stored_password)  # Debugging

            if stored_password.startswith("scrypt"):
                print("Using scrypt verification")  # Debugging
                from werkzeug.security import check_password_hash
                if check_password_hash(stored_password, password):
                    session["user_id"] = str(user["_id"])
                    flash("Login successful!", "success")
                    return redirect(url_for("dashboard"))
                else:
                    flash("Invalid email or password.", "danger")
            else:
                print("Using bcrypt verification")  # Debugging
                if bcrypt.check_password_hash(stored_password, password):
                    session["user_id"] = str(user["_id"])
                    flash("Login successful!", "success")
                    return redirect(url_for("dashboard"))
                else:
                    flash("Invalid email or password.", "danger")
        else:
            flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email").strip().lower()
        
        # Check if user exists
        user = users_collection.find_one({"email": email})
        if user:
            token = str(uuid.uuid4())  # Generate a unique token
            users_collection.update_one({"email": email}, {"$set": {"reset_token": token}})
            
            reset_link = url_for("reset_password", token=token, _external=True)
            print(f"🔗 Reset Link: {reset_link}")  # Debugging - Check if the link is generated

            # Send email
            send_email(
                to_email=email,
                subject="Password Reset Request",
                body=f"Click the link below to reset your password:\n\n{reset_link}"
            )

            flash(f"Password reset link sent to {email}.", "success")
        else:
            flash("Email not found.", "danger")

    return render_template("forgot_password.html")



@app.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = users_collection.find_one({"reset_token": token})

    if not user:
        flash("Invalid or expired reset token.", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        new_password = request.form.get("password")
        hashed_password = generate_password_hash(new_password)

        # Update password in DB and remove token
        users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"password": hashed_password}, "$unset": {"reset_token": ""}}
        )

        flash("Your password has been reset successfully! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html", token=token)



# ✅ Dashboard Route
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    user_id = session["user_id"]
    user = users_collection.find_one({"_id": ObjectId(user_id)})

    if user["role"] == "tutor":
        # ✅ Fetch PENDING sessions for tutors
        tutor_sessions = list(sessions_collection.find({
            "tutor_id": user_id,
            "status": "Pending"
        }))

        for sess in tutor_sessions:
            student = users_collection.find_one({"_id": ObjectId(sess["student_id"])})
            sess["student_name"] = f"{student['first_name']} {student['last_name']}" if student else "Unknown"

        return render_template("dashboard.html", user=user, sessions=tutor_sessions)

    # ✅ Fetch sessions for students (Pending & Accepted)
    student_sessions = list(sessions_collection.find({
        "student_id": user_id,
        "status": {"$in": ["Pending", "Accepted"]}
    }))

    for sess in student_sessions:
        if "tutor_id" in sess:  # Ensure tutor_id exists
            tutor = users_collection.find_one({"_id": ObjectId(sess["tutor_id"])})
            sess["tutor_name"] = f"{tutor['first_name']} {tutor['last_name']}" if tutor else "Unknown"

    return render_template("dashboard.html", user=user, sessions=student_sessions)




# ✅ Logout Route
@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Logged out successfully!", "success")
    return redirect(url_for("home"))



from datetime import datetime, timedelta

def generate_time_slots(start, end, interval=60):
    """Generate time slots from start_time to end_time with a given interval (in minutes)."""
    start_time = datetime.strptime(start, "%H:%M")
    end_time = datetime.strptime(end, "%H:%M")
    slots = []
    
    while start_time < end_time:
        next_time = start_time + timedelta(minutes=interval)
        slots.append(f"{start_time.strftime('%I:%M %p')} - {next_time.strftime('%I:%M %p')}")
        start_time = next_time
    
    return slots

@app.route('/book_session', methods=['GET', 'POST'])
def book_session():
    units = ["Introduction to Programming", "Object-Oriented Programming", "Web Development", 
             "Database Management Systems", "Software Engineering Principles"]

    if request.method == 'POST':
        student_id = session.get('user_id')  # Ensure user is logged in
        unit = request.form.get('unit')
        tutor_id = request.form.get('tutor')

        if student_id and unit and tutor_id:
            # Store the booking in the 'bookings' collection
            bookings_collection.insert_one({
                "student_id": student_id,
                "tutor_id": tutor_id,
                "unit": unit,
                "status": "Pending"
            })

            flash("Session booked successfully!", "success")
            return redirect(url_for('dashboard'))

    selected_unit = request.args.get('unit', '')

    # Fetch tutors who teach the selected unit
    tutors = list(users_collection.find({"role": "tutor"}))
    for tutor in tutors:
        tutor["_id"] = str(tutor["_id"])  # Convert ObjectId to string

    # Ensure only tutors who have availability are shown
    tutor_ids = [tutor["_id"] for tutor in tutors]
    availability_data = availability_collection.find({"tutor_id": {"$in": tutor_ids}})
    
    # Map availability to tutor IDs
    availability = {str(av["tutor_id"]): "Available" for av in availability_data}

    # Filter tutors to only show those with availability
    available_tutors = [tutor for tutor in tutors if tutor["_id"] in availability]

    return render_template('book_session.html',
                           units=units,
                           selected_subject=selected_unit,
                           tutors=available_tutors,
                           availability=availability)



@app.route('/cancel_session/<session_id>', methods=['POST'])
def cancel_session(session_id):
    print(f"Received session_id: {session_id}")  # Debugging
    
    try:
        session = mongo.db.bookings.find_one({"_id": ObjectId(session_id)})  # Try ObjectId
    except:
        session = mongo.db.bookings.find_one({"_id": session_id})  # Try string _id

    if session:
        mongo.db.bookings.delete_one({"_id": session["_id"]})
        flash("Session has been canceled successfully.", "success")
    else:
        flash("Session not found.", "error")

    return redirect(url_for('dashboard'))



    
# ✅ Send Email Function
def send_email(to_email, subject, body):
    msg = Message(subject, recipients=[to_email])
    msg.body = body
    mail.send(msg)

# ✅ Set Availability Route
@app.route("/set_availability", methods=["GET", "POST", "DELETE"])
def set_availability():
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))
    
    tutor = users_collection.find_one({"_id": ObjectId(session["user_id"])})
    if tutor["role"] != "tutor":
        flash("Only tutors can manage availability.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        selected_dates = request.form.get("selected_dates").split(",")
        start_time = request.form.get("start_time_value")
        end_time = request.form.get("end_time_value")

        if not selected_dates or not start_time or not end_time:
            flash("All fields are required.", "danger")
            return redirect(url_for("set_availability"))

        start_date, end_date = selected_dates
        current_date = datetime.strptime(start_date, "%Y-%m-%d")
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")

        while current_date <= end_date_obj:
            availability_data = {
                "tutor_id": str(tutor["_id"]),
                "date": current_date.strftime("%Y-%m-%d"),
                "start_time": start_time,
                "end_time": end_time
            }
            availability_collection.insert_one(availability_data)
            current_date += timedelta(days=1)

        flash("Availability set successfully!", "success")
        return redirect(url_for("dashboard"))
    
    if request.method == "DELETE":
        data = request.get_json()
        availability_id = data.get("availability_id")

        if not availability_id:
            return jsonify({"error": "Availability ID is required"}), 400

        result = availability_collection.delete_one({"_id": ObjectId(availability_id)})

        if result.deleted_count == 1:
            return jsonify({"message": "Availability deleted successfully"}), 200
        else:
            return jsonify({"error": "Availability not found"}), 404

    availabilities = list(availability_collection.find({"tutor_id": str(tutor["_id"])}))

    return render_template("set_availability.html", availabilities=availabilities)


@app.route("/tutor_sessions")
def tutor_sessions():
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    tutor = users_collection.find_one({"_id": ObjectId(session["user_id"])})

    if not tutor or tutor["role"] != "tutor":
        flash("Only tutors can access this page.", "danger")
        return redirect(url_for("dashboard"))

    tutor_id_str = str(tutor["_id"])

    # ✅ Fetch only PENDING sessions for this tutor
    sessions = list(sessions_collection.find({
        "tutor_id": tutor_id_str,
        "status": "Pending"
    }))

    return render_template("dashboard.html", user=tutor, sessions=sessions)





@app.route("/update_session/<session_id>", methods=["POST"])
def update_session(session_id):
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    tutor = users_collection.find_one({"_id": ObjectId(session["user_id"])})
    
    if not tutor or tutor["role"] != "tutor":
        flash("Only tutors can update sessions.", "danger")
        return redirect(url_for("dashboard"))

    session_data = sessions_collection.find_one({"_id": ObjectId(session_id)})

    if not session_data:
        flash("Session not found.", "danger")
        return redirect(url_for("tutor_sessions"))

    status = request.form.get("status")
    phone_number = request.form.get("phone_number", "").strip()
    meeting_link = request.form.get("meeting_link", "").strip()
    venue = request.form.get("venue", "").strip()
    additional_notes = request.form.get("additional_notes", "").strip()

    if not status:
        flash("Status is required.", "danger")
        return redirect(url_for("tutor_sessions"))

    # ✅ Update only the provided fields
    update_data = {"status": status}
    
    if phone_number:
        update_data["phone_number"] = phone_number
    if meeting_link:
        update_data["meeting_link"] = meeting_link
    if venue:
        update_data["venue"] = venue
    if additional_notes:
        update_data["additional_notes"] = additional_notes

    sessions_collection.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": update_data}
    )

    flash(f"Session {status} successfully!", "success")

    return redirect(url_for("tutor_sessions"))



@app.route('/student_dashboard')
def student_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    user = users_collection.find_one({"_id": ObjectId(user_id)})

    # Fetch all accepted sessions for this student
    sessions = list(sessions_collection.find({
        "student_id": str(user_id), 
        "status": "Accepted"
    }))

    return render_template('student_dashboard.html', user=user, sessions=sessions)


def send_email(to_email, subject, body):
    # Use Flask-Mail or another email service
    pass  # Implement email logic


if __name__ == "__main__":
    app.run(debug=True)