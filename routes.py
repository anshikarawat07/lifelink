from flask import render_template, request, redirect, url_for, flash, session
from datetime import datetime
from db_helpers import query_db
from db import get_db
import sqlite3


def register_routes(app):
    # ----------------- AUTH / COMMON ROUTES -----------------

    @app.route("/")
    def home():
        # Redirect based on role
        if "role" in session:
            if session["role"] == "admin":
                return redirect("/admin_dashboard")
            if session["role"] == "user":
                return redirect("/user_dashboard")
        return render_template("home.html")

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        # Register new user
        if request.method == "POST":
            username = request.form["username"]
            password = request.form["password"]
            role = request.form["role"]

            conn = get_db()
            cur = conn.cursor()
            try:
                cur.execute(
                    "INSERT INTO Users (username, password, role) VALUES (?, ?, ?)",
                    (username, password, role),
                )
                conn.commit()
                flash("✅ Signup successful! Please log in.")
                return redirect("/login")
            except sqlite3.IntegrityError:
                flash("⚠ Username already exists. Try another one.")
            finally:
                conn.close()

        return render_template("signup.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        # Authenticate and redirect by role
        if request.method == "POST":
            username = request.form["username"]
            password = request.form["password"]

            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM Users WHERE username=? AND password=?", (username, password)
            )
            user = cur.fetchone()
            conn.close()

            if user:
                session["user_id"] = user[0]
                session["username"] = user[1]
                session["role"] = user[3]

                if user[3] == "admin":
                    return redirect("/admin_dashboard")
                return redirect("/user_dashboard")
            else:
                flash("⚠ Invalid username or password!")

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        # Clear session
        session.clear()
        flash("Logged out successfully.")
        return redirect("/login")

    # ----------------- ADMIN DASHBOARD -----------------

    @app.route("/admin_dashboard")
    def admin_dashboard():
        # require admin
        if "username" not in session:
            flash("⚠ Please login first.")
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            flash("⚠ Access denied. Admins only.")
            return redirect(url_for("login"))

        # dashboard stats
        donors = query_db("SELECT COUNT(*) FROM Donor", one=True)[0]
        stock = query_db("SELECT SUM(available_units) FROM BloodStock", one=True)[0] or 0
        pending = query_db(
            "SELECT COUNT(*) FROM Request WHERE status IN ('Pending', 'Partially Fulfilled')",
            one=True,
        )[0]
        fulfilled = query_db("SELECT COUNT(*) FROM Request WHERE status='Fulfilled'", one=True)[0]
        partial = query_db(
            "SELECT COUNT(*) FROM Request WHERE status='Partially Fulfilled'", one=True
        )[0]
        expired_removed = 0

        stock_data = query_db("SELECT blood_group, available_units FROM BloodStock")
        chart_labels = [row[0] for row in stock_data]
        chart_values = [row[1] for row in stock_data]

        requests = query_db(
            """
            SELECT recipient_name, blood_group, req_units, status, fulfilled_units
            FROM Request
            ORDER BY request_id DESC
            LIMIT 5
            """
        )

        notifications = (
            query_db(
                """
            SELECT title, message, created_at
            FROM Notifications
            ORDER BY created_at DESC
            LIMIT 10
            """
            )
            or []
        )

        camps = (
            query_db(
                """
            SELECT camp_name, location, camp_date, total_donations, total_units
            FROM Camp
            ORDER BY camp_date DESC
            LIMIT 10
            """
            )
            or []
        )

        return render_template(
            "admin_dashboard.html",
            username=session["username"],
            donors=donors,
            stock=stock,
            pending=pending,
            fulfilled=fulfilled,
            partial=partial,
            expired=expired_removed,
            chart_labels=chart_labels,
            chart_values=chart_values,
            requests=requests,
            notifications=notifications,
            camps=camps,
        )

    # ----------------- DONORS (ADMIN) -----------------

    @app.route("/donors", methods=["GET", "POST"])
    def donors():
        # require admin
        if session.get("role") != "admin":
            flash("Access denied.")
            return redirect(url_for("login"))

        conn = get_db()
        cur = conn.cursor()

        # camps for dropdown
        cur.execute("SELECT camp_name, location FROM Camp ORDER BY camp_date DESC")
        camps = cur.fetchall()

        message = None
        if request.method == "POST":
            name = request.form["name"]
            blood_group = request.form["blood_group"]
            contact = request.form.get("contact", "")
            city = request.form.get("city", "")
            aadhaar = request.form["aadhaar"]
            camp_location = request.form.get("camp_location", "")

            existing = query_db("SELECT * FROM Donor WHERE aadhaar = ?", (aadhaar,), one=True)
            if existing:
                message = "⚠ Donor with this Aadhaar number already exists!"
            else:
                cur.execute(
                    """
                    INSERT INTO Donor (name, blood_group, contact, city, aadhaar, camp_location)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (name, blood_group, contact, city, aadhaar, camp_location),
                )
                conn.commit()
                message = "✅ Donor added successfully!"

        cur.execute(
            """
            SELECT donor_id, name, blood_group, contact, city, aadhaar, camp_location
            FROM Donor
            ORDER BY donor_id ASC
            """
        )
        donors = cur.fetchall()
        conn.close()

        return render_template("donors.html", donors=donors, message=message, camps=camps)

    # ----------------- RECORD DONATION (ADMIN) -----------------

    @app.route("/record_donation", methods=["GET", "POST"])
    def record_donation():
        # require admin
        if session.get("role") != "admin":
            flash("Access denied.")
            return redirect(url_for("login"))

        conn = get_db()
        cur = conn.cursor()
        message = None

        # donors & camps lists
        cur.execute("SELECT donor_id, name, blood_group FROM Donor ORDER BY name ASC")
        donors = cur.fetchall()
        cur.execute("SELECT camp_id, camp_name, location FROM Camp ORDER BY camp_date DESC")
        camps = cur.fetchall()

        if request.method == "POST":
            donor_id = request.form.get("donor_id")
            amount = request.form.get("amount")
            camp_id = request.form.get("camp_id")
            date = datetime.now().strftime("%Y-%m-%d")

            if not donor_id or not amount:
                message = "⚠ Please fill all required fields."
            else:
                donor = query_db("SELECT blood_group, name FROM Donor WHERE donor_id=?", (donor_id,), one=True)
                if not donor:
                    message = "⚠ Donor not found!"
                else:
                    blood_group, donor_name = donor
                    try:
                        # camp display text
                        if camp_id:
                            cur.execute("SELECT camp_name, location FROM Camp WHERE camp_id=?", (camp_id,))
                            camp = cur.fetchone()
                            camp_display = f"{camp[0]} — {camp[1]}" if camp else "N/A"
                        else:
                            camp_display = "N/A"

                        # insert donation
                        cur.execute(
                            """
                            INSERT INTO Donation (donor_id, amount, donation_date, camp_location)
                            VALUES (?, ?, ?, ?)
                            """,
                            (donor_id, amount, date, camp_display),
                        )

                        # update donor camp
                        cur.execute("UPDATE Donor SET camp_location=? WHERE donor_id=?", (camp_display, donor_id))

                        # update stock
                        cur.execute("SELECT available_units FROM BloodStock WHERE blood_group=?", (blood_group,))
                        row = cur.fetchone()
                        if row:
                            cur.execute(
                                """
                                UPDATE BloodStock
                                SET available_units = available_units + ?
                                WHERE blood_group=?
                                """,
                                (amount, blood_group),
                            )
                        else:
                            cur.execute(
                                """
                                INSERT INTO BloodStock (blood_group, available_units)
                                VALUES (?, ?)
                                """,
                                (blood_group, amount),
                            )

                        # update camp totals
                        if camp_id:
                            cur.execute(
                                """
                                UPDATE Camp
                                SET total_donations = total_donations + 1,
                                    total_units = total_units + ?
                                WHERE camp_id = ?
                                """,
                                (amount, camp_id),
                            )

                        conn.commit()
                        message = f"✅ Recorded donation for {donor_name} ({blood_group}). Updated camp totals successfully."
                    except sqlite3.Error as e:
                        conn.rollback()
                        message = f"⚠ Database error: {e}"

        # latest donations
        cur.execute(
            """
            SELECT d.donation_id, dn.name, dn.blood_group, d.amount, d.camp_location, d.donation_date
            FROM Donation d
            JOIN Donor dn ON d.donor_id = dn.donor_id
            ORDER BY d.donation_id DESC
            """
        )
        donations = cur.fetchall()
        conn.close()

        return render_template(
            "record_donation.html", donors=donors, camps=camps, donations=donations, message=message
        )

    # ----------------- REQUESTS (ADMIN) -----------------

    @app.route("/requests", methods=["GET", "POST"])
    def requests_page():
        # require admin
        if session.get("role") != "admin":
            flash("Access denied.")
            return redirect(url_for("login"))

        if request.method == "POST":
            recipient_id = request.form.get("recipient_id")
            req_units = int(request.form.get("req_units"))

            recipient = query_db(
                "SELECT name, blood_group FROM Recipient WHERE recipient_id=?", (recipient_id,), one=True
            )
            if not recipient:
                flash("⚠ Invalid Recipient ID. Please check and try again.")
                return redirect(url_for("requests_page"))

            name, group = recipient
            available = query_db("SELECT available_units FROM BloodStock WHERE blood_group=?", (group,), one=True)
            available_units = available[0] if available else 0

            # fulfill logic
            if available_units >= req_units:
                query_db(
                    """
                    INSERT INTO Request (recipient_name, blood_group, req_units, fulfilled_units, status)
                    VALUES (?, ?, ?, ?, 'Fulfilled')
                    """,
                    (name, group, req_units, req_units),
                )
                query_db("UPDATE BloodStock SET available_units = available_units - ? WHERE blood_group=?", (req_units, group))
                flash(f"✅ Request fulfilled successfully for {group}.")
            elif available_units > 0:
                query_db(
                    """
                    INSERT INTO Request (recipient_name, blood_group, req_units, fulfilled_units, status)
                    VALUES (?, ?, ?, ?, 'Partially Fulfilled')
                    """,
                    (name, group, req_units, available_units),
                )
                query_db("UPDATE BloodStock SET available_units = 0 WHERE blood_group=?", (group,))
                flash(f"⚠ Only partially fulfilled ({available_units} ml).")
            else:
                query_db(
                    """
                    INSERT INTO Request (recipient_name, blood_group, req_units, fulfilled_units, status)
                    VALUES (?, ?, ?, 0, 'Pending')
                    """,
                    (name, group, req_units),
                )
                flash(f"⚠ No stock for {group}. Request pending.")

            return redirect(url_for("requests_page"))

        reqs = query_db("SELECT * FROM Request ORDER BY request_id DESC")
        return render_template("requests.html", requests=reqs)

    # ----------------- RECIPIENTS (ADMIN) -----------------

    @app.route("/recipients", methods=["GET", "POST"])
    def recipients():
        # require admin
        if session.get("role") != "admin":
            flash("Access denied.")
            return redirect(url_for("login"))

        message = None
        if request.method == "POST":
            name = request.form["name"]
            blood_group = request.form["blood_group"]
            contact = request.form.get("contact", "")
            aadhaar = request.form["aadhaar"]

            existing = query_db("SELECT * FROM Recipient WHERE aadhaar = ?", (aadhaar,), one=True)
            if existing:
                message = "⚠ Recipient with this Aadhaar number already exists!"
            else:
                query_db(
                    "INSERT INTO Recipient (name, blood_group, contact, aadhaar) VALUES (?, ?, ?, ?)",
                    (name, blood_group, contact, aadhaar),
                )
                message = "✅ Recipient added successfully!"

        recipients = query_db("SELECT * FROM Recipient ORDER BY recipient_id ASC")
        return render_template("recipients.html", recipients=recipients, message=message)

    # ----------------- USER DASHBOARD -----------------

    @app.route("/user_dashboard")
    def user_dashboard():
        # require user
        if "role" not in session or session.get("role") != "user":
            flash("⚠ Access denied.")
            return redirect("/login")

        conn = get_db()
        cur = conn.cursor()
        user_id = session["user_id"]
        username = session["username"]

        # ensure user exists
        cur.execute("SELECT user_id FROM Users WHERE user_id=?", (user_id,))
        user_exists = cur.fetchone()
        if not user_exists:
            flash("⚠ User record missing in database. Please re-login.")
            conn.close()
            return redirect("/logout")

        # get donor linked to user
        cur.execute("SELECT donor_id, blood_group FROM Donor WHERE user_id=?", (user_id,))
        donor_row = cur.fetchone()

        if donor_row:
            donor_id, blood_group = donor_row
        else:
            # try by username and link
            cur.execute("SELECT donor_id, blood_group FROM Donor WHERE name=?", (username,))
            name_row = cur.fetchone()
            if name_row:
                donor_id, blood_group = name_row
                cur.execute("UPDATE Donor SET user_id=? WHERE donor_id=?", (user_id, donor_id))
                conn.commit()
            else:
                # create temporary donor record
                temp_aadhaar = f"TEMP{datetime.now().timestamp()}"
                try:
                    cur.execute(
                        """
                        INSERT INTO Donor (user_id, name, blood_group, contact, city, camp_location, aadhaar)
                        VALUES (?, ?, 'Unknown', '', '', NULL, ?)
                        """,
                        (user_id, username, temp_aadhaar),
                    )
                except sqlite3.IntegrityError:
                    cur.execute(
                        """
                        INSERT INTO Donor (user_id, name, blood_group, contact, city, camp_location, aadhaar)
                        VALUES (NULL, ?, 'Unknown', '', '', NULL, ?)
                        """,
                        (username, temp_aadhaar),
                    )

                conn.commit()
                donor_id = cur.lastrowid
                blood_group = "Unknown"

        # donor stats
        cur.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(amount), 0), MAX(donation_date)
            FROM Donation
            WHERE donor_id = ?
            """,
            (donor_id,),
        )
        total_donations, total_units, last_donation = cur.fetchone()
        last_donation = last_donation or "—"

        # donation history
        cur.execute(
            """
            SELECT donation_date, amount
            FROM Donation
            WHERE donor_id = ?
            ORDER BY donation_date
            """,
            (donor_id,),
        )
        donation_data = cur.fetchall()
        donation_dates = [d[0] for d in donation_data]
        donation_values = [d[1] for d in donation_data]

        # recent user requests
        cur.execute(
            """
            SELECT request_id, blood_group, req_units, status
            FROM Request
            WHERE recipient_name=?
            ORDER BY request_id DESC LIMIT 5
            """,
            (username,),
        )
        user_requests = cur.fetchall()

        # notifications
        cur.execute(
            """
            SELECT title, message, created_at
            FROM Notifications
            ORDER BY created_at DESC LIMIT 5
            """
        )
        notifications = cur.fetchall()

        # user's registered camps
        cur.execute(
            """
            SELECT c.camp_name, c.location, c.camp_date, c.total_donations, c.total_units
            FROM Camp c
            JOIN CampRegistrations r ON c.camp_id = r.camp_id
            WHERE r.user_id = ?
            ORDER BY c.camp_date DESC
            """,
            (user_id,),
        )
        user_camps = cur.fetchall()
        conn.close()

        return render_template(
            "user_dashboard.html",
            user_name=username,
            user_blood_group=blood_group or "Unknown",
            total_donations=total_donations or 0,
            total_units=total_units or 0,
            last_donation=last_donation,
            donation_dates=donation_dates,
            donation_values=donation_values,
            user_requests=user_requests,
            notifications=notifications,
            user_camps=user_camps,
        )

    # ----------------- NOTIFICATIONS (ADMIN) -----------------

    @app.route("/send_notification", methods=["GET", "POST"])
    def send_notification():
        # require admin
        if session.get("role") != "admin":
            flash("Access denied.")
            return redirect(url_for("login"))

        conn = get_db()
        cur = conn.cursor()

        if request.method == "POST":
            title = request.form["title"]
            message = request.form["message"]

            if not title or not message:
                flash("⚠ Please fill in both Title and Message fields.")
            else:
                cur.execute("INSERT INTO Notifications (title, message) VALUES (?, ?)", (title, message))
                conn.commit()
                flash("✅ Notification sent successfully to all users.")

            return redirect(url_for("send_notification"))

        # recent notifications
        cur.execute("SELECT title, message, created_at FROM Notifications ORDER BY created_at DESC LIMIT 10")
        notifications = cur.fetchall()
        conn.close()
        return render_template("send_notification.html", notifications=notifications)

    # ----------------- CAMPS (ADMIN) -----------------

    @app.route("/add_camp", methods=["GET", "POST"])
    def add_camp():
        # require admin
        if session.get("role") != "admin":
            flash("Access denied.")
            return redirect("/login")

        conn = get_db()
        cur = conn.cursor()

        if request.method == "POST":
            camp_name = request.form.get("camp_name", "").strip()
            location = request.form.get("location", "").strip()
            camp_date = request.form.get("camp_date", "").strip()

            if not camp_name or not location or not camp_date:
                flash("⚠ Please fill in all fields.")
            else:
                try:
                    cur.execute("INSERT INTO Camp (camp_name, location, camp_date) VALUES (?, ?, ?)",
                                (camp_name, location, camp_date))
                    conn.commit()
                    flash("✅ Camp added successfully!")
                    return redirect("/add_camp")
                except sqlite3.Error as e:
                    conn.rollback()
                    flash(f"⚠ Database error: {e}")

        cur.execute(
            """
            SELECT camp_name, location, camp_date, total_donations, total_units
            FROM Camp
            ORDER BY camp_date DESC
            """
        )
        camps = cur.fetchall()
        conn.close()
        return render_template("add_camp.html", camps=camps)

    # ----------------- DONATE (USER: CAMP REGISTRATION) -----------------

    @app.route("/donate", methods=["GET", "POST"])
    def donate_blood():
        # require login
        if "username" not in session:
            flash("Please login first.")
            return redirect("/login")

        conn = get_db()
        cur = conn.cursor()
        username = session["username"]
        user_id = session["user_id"]

        # upcoming camps
        cur.execute(
            """
            SELECT camp_id, camp_name, location, camp_date
            FROM Camp
            WHERE date(camp_date) >= date('now')
            ORDER BY camp_date ASC
            """
        )
        camps = cur.fetchall()

        if request.method == "POST":
            camp_id = request.form.get("camp_id")
            amount = request.form.get("amount")

            if not camp_id or not amount:
                flash("⚠ Please select a camp and enter donation amount.")
            else:
                try:
                    # register for camp
                    cur.execute(
                        """
                        INSERT INTO CampRegistrations (camp_id, user_id, donor_name, amount, mode, status)
                        VALUES (?, ?, ?, ?, 'online', 'Confirmed')
                        """,
                        (camp_id, user_id, username, amount),
                    )

                    # donor linked info
                    cur.execute("SELECT donor_id, blood_group FROM Donor WHERE user_id=?", (user_id,))
                    donor = cur.fetchone()
                    if donor:
                        donor_id, blood_group = donor
                    else:
                        donor_id = None
                        blood_group = "Unknown"

                    # record donation
                    date = datetime.now().strftime("%Y-%m-%d")
                    cur.execute(
                        """
                        INSERT INTO Donation (donor_id, amount, donation_date, camp_location)
                        VALUES (?, ?, ?, (SELECT location FROM Camp WHERE camp_id=?))
                        """,
                        (donor_id, amount, date, camp_id),
                    )

                    # update stock
                    cur.execute("SELECT available_units FROM BloodStock WHERE blood_group=?", (blood_group,))
                    stock = cur.fetchone()
                    if stock:
                        cur.execute(
                            """
                            UPDATE BloodStock
                            SET available_units = available_units + ?
                            WHERE blood_group=?
                            """,
                            (amount, blood_group),
                        )
                    else:
                        cur.execute(
                            """
                            INSERT INTO BloodStock (blood_group, available_units)
                            VALUES (?, ?)
                            """,
                            (blood_group, amount),
                        )

                    # update camp totals
                    cur.execute(
                        """
                        UPDATE Camp
                        SET total_donations = total_donations + 1,
                            total_units = total_units + ?
                        WHERE camp_id = ?
                        """,
                        (amount, camp_id),
                    )

                    conn.commit()
                    flash("✅ Donation recorded successfully and camp updated!")
                except sqlite3.IntegrityError:
                    flash("⚠ You already registered for this camp.")
                except sqlite3.Error as e:
                    conn.rollback()
                    flash(f"⚠ Database error: {e}")

            conn.close()
            return redirect("/user_dashboard")

        conn.close()
        return render_template("donate.html", camps=camps)

    # ----------------- REQUEST BLOOD (USER) -----------------

    @app.route("/request_blood", methods=["GET", "POST"])
    def request_blood():
        # require login
        if "username" not in session:
            flash("Please login first.")
            return redirect("/login")

        conn = get_db()
        cur = conn.cursor()
        username = session["username"]
        user_id = session["user_id"]

        # get user's blood group
        cur.execute("SELECT blood_group FROM Donor WHERE user_id=?", (user_id,))
        donor = cur.fetchone()
        if donor and donor[0] not in (None, "", "Unknown"):
            blood_group = donor[0]
        else:
            flash("⚠ Please update your blood group in your profile before requesting blood.")
            conn.close()
            return redirect("/profile")

        # ensure Recipient record exists
        cur.execute("SELECT recipient_id FROM Recipient WHERE name=?", (username,))
        recipient = cur.fetchone()
        if not recipient:
            temp_aadhaar = f"TEMP{datetime.now().timestamp()}"
            cur.execute(
                """
                INSERT INTO Recipient (name, blood_group, contact, aadhaar)
                VALUES (?, ?, ?, ?)
                """,
                (username, blood_group, "", temp_aadhaar),
            )
            conn.commit()

        message = None
        if request.method == "POST":
            try:
                req_units = int(request.form.get("req_units", 0))
            except (TypeError, ValueError):
                flash("⚠ Please enter a valid number for blood units.")
                conn.close()
                return redirect("/request_blood")

            if req_units <= 0:
                flash("⚠ Please enter a valid amount of blood (in ml).")
                conn.close()
                return redirect("/request_blood")

            # check stock
            cur.execute("SELECT available_units FROM BloodStock WHERE blood_group=?", (blood_group,))
            stock = cur.fetchone()
            available_units = stock[0] if stock else 0
            request_date = datetime.now().strftime("%Y-%m-%d")

            if available_units >= req_units:
                cur.execute(
                    """
                    INSERT INTO Request (recipient_name, blood_group, req_units, fulfilled_units, status, request_date)
                    VALUES (?, ?, ?, ?, 'Fulfilled', ?)
                    """,
                    (username, blood_group, req_units, req_units, request_date),
                )
                cur.execute("UPDATE BloodStock SET available_units = available_units - ? WHERE blood_group=?",
                            (req_units, blood_group))
                message = f"✅ Request fulfilled successfully for {blood_group}."
            elif available_units > 0:
                cur.execute(
                    """
                    INSERT INTO Request (recipient_name, blood_group, req_units, fulfilled_units, status, request_date)
                    VALUES (?, ?, ?, ?, 'Partially Fulfilled', ?)
                    """,
                    (username, blood_group, req_units, available_units, request_date),
                )
                cur.execute("UPDATE BloodStock SET available_units = 0 WHERE blood_group=?", (blood_group,))
                message = f"⚠ Only partially fulfilled ({available_units} ml available)."
            else:
                cur.execute(
                    """
                    INSERT INTO Request (recipient_name, blood_group, req_units, fulfilled_units, status, request_date)
                    VALUES (?, ?, ?, 0, 'Pending', ?)
                    """,
                    (username, blood_group, req_units, request_date),
                )
                message = f"⚠ No stock for {blood_group}. Your request is pending."

            conn.commit()
            flash(message)
            conn.close()
            return redirect(url_for("user_dashboard"))

        conn.close()
        return render_template("request_blood.html", group=blood_group, message=message)

    # ----------------- PROFILE (USER) -----------------

    @app.route("/profile", methods=["GET", "POST"])
    def profile():
        # require login
        if "user_id" not in session:
            flash("Please log in first.")
            return redirect("/login")

        conn = get_db()
        cur = conn.cursor()
        user_id = session["user_id"]

        # find donor linked to user
        cur.execute("SELECT donor_id FROM Donor WHERE user_id=?", (user_id,))
        donor = cur.fetchone()
        donor_id = donor[0] if donor else None

        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            age = request.form.get("age", None)
            gender = request.form.get("gender", "")
            email = request.form.get("email", "")
            address = request.form.get("address", "")
            blood_group = request.form.get("blood_group", "")
            city = request.form.get("city", "")
            contact = request.form.get("contact", "")
            aadhaar = request.form.get("aadhaar", "").strip()

            try:
                if not donor_id:
                    # create donor record
                    cur.execute(
                        """
                        INSERT INTO Donor (user_id, name, blood_group, contact, city, aadhaar)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (user_id, full_name or session["username"], blood_group, contact, city, aadhaar),
                    )
                    donor_id = cur.lastrowid
                else:
                    # update donor
                    cur.execute(
                        """
                        UPDATE Donor
                        SET name=?, blood_group=?, contact=?, city=?, aadhaar=?
                        WHERE donor_id=?
                        """,
                        (full_name or session["username"], blood_group, contact, city, aadhaar, donor_id),
                    )

                # upsert DonorProfile
                cur.execute("SELECT donor_id FROM DonorProfile WHERE donor_id=?", (donor_id,))
                existing = cur.fetchone()
                if existing:
                    cur.execute(
                        """
                        UPDATE DonorProfile
                        SET full_name=?, age=?, gender=?, email=?, address=?
                        WHERE donor_id=?
                        """,
                        (full_name, age, gender, email, address, donor_id),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO DonorProfile (donor_id, full_name, age, gender, email, address)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (donor_id, full_name, age, gender, email, address),
                    )

                conn.commit()
                flash("✅ Profile updated successfully!")
            except sqlite3.IntegrityError:
                flash("⚠ This Aadhaar number is already used by another user.")
            except sqlite3.Error as e:
                flash(f"⚠ Database error: {e}")

        # retrieve profile data
        if donor_id:
            cur.execute(
                """
                SELECT d.name, d.blood_group, d.contact, d.city, d.aadhaar,
                    p.full_name, p.age, p.gender, p.email, p.address
                FROM Donor d
                LEFT JOIN DonorProfile p ON d.donor_id = p.donor_id
                WHERE d.donor_id=?
                """,
                (donor_id,),
            )
            data = cur.fetchone()
        else:
            data = [None] * 10

        conn.close()

        return render_template(
            "profile.html",
            full_name=data[5] or "Not Provided",
            age=data[6] or "-",
            gender=data[7] or "-",
            blood_group=data[1] or "Not Updated",
            city=data[3] or "-",
            contact=data[2] or "-",
            email=data[8] or "-",
            address=data[9] or "-",
            aadhaar=data[4] or "-",
        )

    # ----------------- CAMP REGISTRATION (ADMIN) -----------------

    @app.route("/camp_register_admin", methods=["GET", "POST"])
    def camp_register_admin():
        # require admin
        if session.get("role") != "admin":
            flash("Access denied.")
            return redirect("/login")

        conn = get_db()
        cur = conn.cursor()

        # today's camps
        cur.execute(
            """
            SELECT camp_id, camp_name, location, camp_date
            FROM Camp
            WHERE date(camp_date) = date('now')
            ORDER BY camp_date
            """
        )
        active_camps = cur.fetchall()

        if request.method == "POST":
            camp_id = request.form.get("camp_id")
            donor_name = request.form.get("donor_name")
            amount = request.form.get("amount")

            if not camp_id or not donor_name or not amount:
                flash("⚠ Please fill all fields.")
            else:
                try:
                    cur.execute(
                        """
                        INSERT INTO CampRegistrations (camp_id, donor_name, amount, mode, status)
                        VALUES (?, ?, ?, 'admin', 'Confirmed')
                        """,
                        (camp_id, donor_name, amount),
                    )

                    # update donation & stock
                    cur.execute("SELECT donor_id, blood_group FROM Donor WHERE name=?", (donor_name,))
                    donor = cur.fetchone()
                    donor_id = donor[0] if donor else None
                    group = donor[1] if donor else "Unknown"

                    if donor_id:
                        cur.execute(
                            "INSERT INTO Donation (donor_id, amount, donation_date) VALUES (?, ?, date('now'))",
                            (donor_id, amount),
                        )
                        cur.execute(
                            """
                            INSERT INTO BloodStock (blood_group, available_units)
                            VALUES (?, ?)
                            ON CONFLICT(blood_group) DO UPDATE
                            SET available_units = available_units + excluded.available_units
                            """,
                            (group, amount),
                        )

                    conn.commit()
                    flash("✅ Walk-in donor registered successfully!")
                except sqlite3.Error as e:
                    conn.rollback()
                    flash(f"⚠ Error: {e}")

            return redirect("/camp_register_admin")

        cur.execute(
            """
            SELECT r.registration_id, r.donor_name, c.camp_name, r.amount, r.mode, r.status, r.registered_on
            FROM CampRegistrations r
            JOIN Camp c ON r.camp_id = c.camp_id
            WHERE date(c.camp_date) = date('now')
            ORDER BY r.registered_on DESC
            """
        )
        registrations = cur.fetchall()
        conn.close()
        return render_template("camp_register_admin.html", active_camps=active_camps, registrations=registrations)

    # ----------------- CAMP REGISTRATIONS (ADMIN) -----------------

    @app.route("/camp_registrations")
    def camp_registrations():
        # require admin
        if session.get("role") != "admin":
            flash("Access denied.")
            return redirect("/login")

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT r.registration_id, r.donor_name, c.camp_name, c.location, c.camp_date,
                r.amount, r.mode, r.status, r.registered_on
            FROM CampRegistrations r
            JOIN Camp c ON r.camp_id = c.camp_id
            ORDER BY r.registered_on DESC
            """
        )
        regs = cur.fetchall()
        conn.close()
        return render_template("camp_registrations.html", regs=regs)
