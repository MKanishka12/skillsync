"""Optional: add 8 demo students and 4 projects so the app has data to demo.

Run once:  python seed_demo.py
All demo accounts use the password:  demo1234
"""
from werkzeug.security import generate_password_hash
from app import app, get_db, init_db, now

STUDENTS = [
    ("Aarav Sharma", "aarav@demo.edu", "Computer Science", 3, "Python, SQL, Flask, Machine Learning", "Artificial Intelligence, Startups", "Backend developer who enjoys turning data into products."),
    ("Meera Iyer", "meera@demo.edu", "Design", 2, "UI Design, Figma, User Research, Prototyping", "Startups, Accessibility", "Designing interfaces people actually enjoy using."),
    ("Rohan Das", "rohan@demo.edu", "Information Technology", 4, "JavaScript, React, HTML, CSS, Flask", "Web Development, Startups", "Full-stack tinkerer, hackathon regular."),
    ("Priya Nair", "priya@demo.edu", "Artificial Intelligence and Data Science", 3, "Python, Machine Learning, Data Analysis, Statistics", "Artificial Intelligence, Healthcare", "Likes clean datasets and honest models."),
    ("Karthik Raja", "karthik@demo.edu", "Electronics and Communication", 2, "Arduino, IoT, C, Embedded Systems", "Robotics, Sustainability", "Builds things that blink, move and measure."),
    ("Sneha Pillai", "sneha@demo.edu", "Business Administration", 4, "Marketing, Public Speaking, Business Planning, Content Writing", "Startups, Social Impact", "Turns ideas into pitches and pitches into plans."),
    ("Vikram Singh", "vikram@demo.edu", "Computer Science", 1, "Java, C, Data Structures, SQL", "Web Development, Gaming", "First year, learning fast."),
    ("Ananya Menon", "ananya@demo.edu", "Biotechnology", 3, "Data Analysis, Python, Lab Research, Statistics", "Healthcare, Sustainability", "Bridging biology and code."),
]
PROJECTS = [
    ("Campus Waste Tracker", "A web dashboard and sensor kit that tracks bin fill levels across campus so cleaning crews can plan routes and the college can measure its waste reduction.", "IoT, Python, Flask, UI Design", 4, "aarav@demo.edu"),
    ("Study Buddy Matcher", "A mobile-friendly app that pairs students for exam preparation based on subjects and timetables, with a simple chat and session planner.", "React, JavaScript, UI Design, Flask", 3, "rohan@demo.edu"),
    ("Health Data Explorer", "Explore anonymised public health datasets with interactive charts and a small prediction model to highlight regional risk factors.", "Python, Machine Learning, Data Analysis, Statistics", 4, "priya@demo.edu"),
    ("Startup Pitch Toolkit", "A guided workspace for student founders: lean canvas, market sizing sheet and pitch deck checklist with feedback from peers.", "Business Planning, Marketing, Public Speaking, Figma", 3, "sneha@demo.edu"),
]

with app.app_context():
    init_db()
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM students").fetchone()[0] > 0:
        print("Database already has students - nothing added.")
    else:
        for n, e, d, y, sk, it, bio in STUDENTS:
            db.execute("INSERT INTO students (name,email,password_hash,department,year,skills,interests,bio,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                       (n, e, generate_password_hash("demo1234"), d, y, sk, it, bio, now()))
        for t, desc, req, size, owner in PROJECTS:
            oid = db.execute("SELECT id FROM students WHERE email=?", (owner,)).fetchone()[0]
            db.execute("INSERT INTO projects (owner_id,title,description,required_skills,team_size,created_at) VALUES (?,?,?,?,?,?)",
                       (oid, t, desc, req, size, now()))
        db.commit()
        print("Added 8 demo students and 4 projects. Log in with e.g. aarav@demo.edu / demo1234")
