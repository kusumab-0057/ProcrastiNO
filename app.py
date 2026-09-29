import json
import os
import sqlite3
from datetime import datetime, date
from urllib.parse import quote_plus
import time

from flask import Flask, render_template, request, session, redirect
from dotenv import load_dotenv
from google import genai


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

app = Flask(__name__)
app.secret_key = "procrastino-secret-key"


# ============================================================
# DATABASE
# ============================================================

def init_db():

    conn = sqlite3.connect("database.db")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject_name TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            topic_name TEXT NOT NULL,
            FOREIGN KEY (subject_id) REFERENCES subjects(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS quiz_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            topic_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (subject_id) REFERENCES subjects(id),
            FOREIGN KEY (topic_id) REFERENCES topics(id)
        )
    """)

    conn.commit()
    conn.close()


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return render_template("index.html")


# ============================================================
# SIGNUP
# ============================================================

@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            return "Passwords do not match!"

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        try:

            cursor.execute(
                """
                INSERT INTO users
                (name, email, password)
                VALUES (?, ?, ?)
                """,
                (name, email, password)
            )

            conn.commit()

        except sqlite3.IntegrityError:

            conn.close()

            return "An account with this email already exists!"

        conn.close()

        return redirect("/login")

    return render_template("signup.html")


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT *
            FROM users
            WHERE email = ?
            AND password = ?
            """,
            (email, password)
        )

        user = cursor.fetchone()

        conn.close()

        if user:

            session["user_id"] = user[0]
            session["user_name"] = user[1]

            return redirect("/intro?next=dashboard")

        return "Invalid email or password!"

    return render_template("login.html")

# ============================================================
# INTRO BEFORE NEXT PAGE
# ============================================================

@app.route("/intro")
def intro():

    next_page = request.args.get("next", "login")

    # Only allow these two destinations.
    if next_page not in ["login", "dashboard"]:
        next_page = "login"

    # Dashboard intro is allowed only after login.
    if next_page == "dashboard" and "user_id" not in session:
        return redirect("/login")

    return render_template(
        "intro.html",
        next_page=next_page
    )

# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # --------------------------------------------------------
    # Total subjects
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM subjects
        WHERE user_id = ?
        """,
        (session["user_id"],)
    )

    subject_count = cursor.fetchone()[0]

    # --------------------------------------------------------
    # Total topics
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM topics
        JOIN subjects
            ON topics.subject_id = subjects.id
        WHERE subjects.user_id = ?
        """,
        (session["user_id"],)
    )

    topic_count = cursor.fetchone()[0]

    # --------------------------------------------------------
    # Total quizzes
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM quiz_results
        WHERE user_id = ?
        """,
        (session["user_id"],)
    )

    quiz_count = cursor.fetchone()[0]

    # --------------------------------------------------------
    # Average score
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT AVG(
            CAST(score AS FLOAT) / total * 100
        )
        FROM quiz_results
        WHERE user_id = ?
        """,
        (session["user_id"],)
    )

    average_score = cursor.fetchone()[0]

    if average_score is None:

        average_score = 0

    else:

        average_score = round(average_score)

    conn.close()

    return render_template(
        "dashboard.html",
        subject_count=subject_count,
        topic_count=topic_count,
        quiz_count=quiz_count,
        average_score=average_score
    )


# ============================================================
# SUBJECTS
# ============================================================

@app.route("/subjects", methods=["GET", "POST"])
def subjects():

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # --------------------------------------------------------
    # ADD SUBJECT
    # --------------------------------------------------------

    if request.method == "POST":

        subject_name = request.form.get("subject_name", "").strip()

        if subject_name:

            cursor.execute(
                """
                INSERT INTO subjects
                (user_id, subject_name)
                VALUES (?, ?)
                """,
                (
                    session["user_id"],
                    subject_name
                )
            )

            conn.commit()

    # --------------------------------------------------------
    # GET SUBJECTS
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT id, subject_name
        FROM subjects
        WHERE user_id = ?
        """,
        (session["user_id"],)
    )

    subjects_list = cursor.fetchall()

    conn.close()

    return render_template(
        "subjects.html",
        subjects=subjects_list
    )


# ============================================================
# DELETE SUBJECT
# ============================================================

@app.route("/delete_subject/<int:subject_id>", methods=["POST"])
def delete_subject(subject_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM topics
        WHERE subject_id = ?
        """,
        (subject_id,)
    )

    cursor.execute(
        """
        DELETE FROM subjects
        WHERE id = ?
        AND user_id = ?
        """,
        (subject_id, session["user_id"])
    )

    conn.commit()
    conn.close()

    return redirect("/subjects")


# ============================================================
# SUBJECT TOPICS
# ============================================================

@app.route("/subject/<int:subject_id>", methods=["GET", "POST"])
def subject_topics(subject_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # --------------------------------------------------------
    # Verify subject belongs to logged-in user
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT id, subject_name
        FROM subjects
        WHERE id = ?
        AND user_id = ?
        """,
        (subject_id, session["user_id"])
    )

    subject = cursor.fetchone()

    if not subject:

        conn.close()

        return "Subject not found!"

    # --------------------------------------------------------
    # Add topic
    # --------------------------------------------------------

    if request.method == "POST":

        topic_name = request.form["topic_name"]

        cursor.execute(
            """
            INSERT INTO topics
            (subject_id, topic_name)
            VALUES (?, ?)
            """,
            (subject_id, topic_name)
        )

        conn.commit()

    # --------------------------------------------------------
    # Get topics
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT id, topic_name
        FROM topics
        WHERE subject_id = ?
        """,
        (subject_id,)
    )

    topics = cursor.fetchall()

    conn.close()

    return render_template(
        "subject_topics.html",
        subject=subject,
        topics=topics
    )


# ============================================================
# DELETE TOPIC
# ============================================================

@app.route(
    "/delete_topic/<int:topic_id>/<int:subject_id>",
    methods=["POST"]
)
def delete_topic(topic_id, subject_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM topics
        WHERE id = ?
        AND subject_id = ?
        AND subject_id IN (
            SELECT id
            FROM subjects
            WHERE user_id = ?
        )
        """,
        (
            topic_id,
            subject_id,
            session["user_id"]
        )
    )

    conn.commit()
    conn.close()

    return redirect(f"/subject/{subject_id}")


# ============================================================
# AI QUIZ GENERATOR
# ============================================================

def generate_questions(subject_name, topic_name):

    subject_lower = subject_name.strip().casefold()

    if "hindi" in subject_lower or "हिंदी" in subject_lower:
        quiz_language = "Hindi"
    elif "telugu" in subject_lower or "తెలుగు" in subject_lower:
        quiz_language = "Telugu"
    else:
        quiz_language = "English"

    prompt = f"""
You are an educational quiz generator.

Create exactly 5 multiple-choice questions about:

{topic_name}

Subject: {subject_name}

Generate the complete quiz in {quiz_language}.

The question text and all four options must be written in {quiz_language}.
If the topic contains technical terms, keep necessary technical terms in their commonly used form.

The questions must specifically test knowledge of the topic.

Return ONLY valid JSON in this exact format:

[
    {{
        "question": "Question text",
        "options": [
            "Option A",
            "Option B",
            "Option C",
            "Option D"
        ],
        "answer": 0
    }}
]

Rules:
- Create exactly 5 questions.
- Each question must have exactly 4 options.
- "answer" must be 0, 1, 2, or 3.
- The answer number must correspond to the correct option.
- Questions must be educational.
- Questions must be directly related to the topic.
"""

    # Try Gemini twice in case of a temporary server error.
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt
            )

            text = response.text.strip()

            # Remove Markdown code fences if Gemini adds them.
            if text.startswith("```"):
                text = text.replace("```json", "", 1)
                text = text.replace("```", "")
                text = text.strip()

            questions = json.loads(text)

            # Validate the AI response before displaying the quiz.
            if (
                isinstance(questions, list)
                and len(questions) == 5
                and all(
                    isinstance(q, dict)
                    and "question" in q
                    and "options" in q
                    and "answer" in q
                    and isinstance(q["options"], list)
                    and len(q["options"]) == 4
                    and q["answer"] in [0, 1, 2, 3]
                    for q in questions
                )
            ):
                return questions

        except Exception as e:
            print(f"Gemini quiz generation attempt {attempt + 1} failed: {e}")

            if attempt == 0:
                time.sleep(2)

    # Gemini was unavailable after both attempts.
    raise RuntimeError(
        "Quiz generation is temporarily unavailable. "
        "Please try again in a moment."
    )


# ============================================================
# QUIZ
# ============================================================

@app.route(
    "/quiz/<int:subject_id>/<int:topic_id>",
    methods=["GET", "POST"]
)
def quiz(subject_id, topic_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # --------------------------------------------------------
    # Get subject
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT id, subject_name
        FROM subjects
        WHERE id = ?
        AND user_id = ?
        """,
        (
            subject_id,
            session["user_id"]
        )
    )

    subject = cursor.fetchone()

    if not subject:

        conn.close()

        return "Subject not found!"

    # --------------------------------------------------------
    # Get topic
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT id, topic_name
        FROM topics
        WHERE id = ?
        AND subject_id = ?
        """,
        (
            topic_id,
            subject_id
        )
    )

    topic = cursor.fetchone()

    conn.close()

    if not topic:

        return "Topic not found!"

    # ========================================================
    # OPEN QUIZ
    # ========================================================

    if request.method == "GET":

        try:
            questions = generate_questions(subject[1], topic[1])

        except Exception as e:
            print(f"Quiz generation failed: {e}")

            return render_template(
                "quiz.html",
                subject=subject,
                topic=topic,
                questions=[],
                error_message=(
                    "Quiz generation is temporarily unavailable. "
                    "Please try again in a moment."
                )
            )

        session["quiz_questions"] = questions

        return render_template(
            "quiz.html",
            subject=subject,
            topic=topic,
            questions=questions
        )

    # ========================================================
    # SUBMIT QUIZ
    # ========================================================

    questions = session.get(
        "quiz_questions",
        []
    )

    score = 0

    for i, question in enumerate(questions):

        selected_answer = request.form.get(
            f"question_{i}"
        )

        if selected_answer is not None:

            correct_answer = question["options"][
                question["answer"]
            ]

            if selected_answer == correct_answer:

                score += 1

    total = len(questions)

    # ========================================================
    # SAVE RESULT
    # ========================================================

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO quiz_results
        (
            user_id,
            subject_id,
            topic_id,
            score,
            total
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            session["user_id"],
            subject_id,
            topic_id,
            score,
            total
        )
    )

    conn.commit()
    conn.close()

    return render_template(
        "quiz_result.html",
        subject=subject,
        topic=topic,
        score=score,
        total=total
    )


# ============================================================
# PERFORMANCE
# ============================================================

@app.route("/performance")
def performance():

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            quiz_results.id,
            subjects.id,
            topics.id,
            subjects.subject_name,
            topics.topic_name,
            quiz_results.score,
            quiz_results.total,
            quiz_results.created_at

        FROM quiz_results

        JOIN subjects
            ON quiz_results.subject_id = subjects.id

        JOIN topics
            ON quiz_results.topic_id = topics.id

        WHERE quiz_results.user_id = ?

        ORDER BY quiz_results.id ASC
        """,
        (session["user_id"],)
    )

    results = cursor.fetchall()

    conn.close()

    # --------------------------------------------------------
    # Calculate percentages
    # --------------------------------------------------------

    percentages = []

    for result in results:

        score = result[5]
        total = result[6]

        if total > 0:

            percentage = (
                score / total
            ) * 100

            percentages.append(percentage)

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    if percentages:

        average_score = round(
            sum(percentages) /
            len(percentages)
        )

        best_score = round(
            max(percentages)
        )

        latest_score = round(
            percentages[-1]
        )

    else:

        average_score = 0
        best_score = 0
        latest_score = 0

    # --------------------------------------------------------
    # Overall performance message
    # --------------------------------------------------------

    if average_score >= 80:

        performance_message = (
            "Excellent performance! 🌟 "
            "Keep challenging yourself."
        )

    elif average_score >= 60:

        performance_message = (
            "Good progress! 👍 "
            "A little more revision can make you stronger."
        )

    elif average_score >= 40:

        performance_message = (
            "You're making progress! 📚 "
            "Focus on revision and practice."
        )

    else:

        performance_message = (
            "Let's strengthen the basics! 🧠 "
            "More practice will help."
        )

    # --------------------------------------------------------
    # Latest quiz
    # --------------------------------------------------------

    latest_result = (
        results[-1]
        if results
        else None
    )

    return render_template(
        "performance.html",
        results=results,
        average_score=average_score,
        best_score=best_score,
        latest_score=latest_score,
        performance_message=performance_message,
        latest_result=latest_result
    )


# ============================================================
# AI RECOMMENDATIONS
# ============================================================

def clean_ai_text(value):
    """Remove simple Markdown characters from AI output."""
    if value is None:
        return ""

    text = str(value)
    text = text.replace("*", "")
    text = text.replace("#", "")
    return text.strip()


def generate_recommendations(subject_name, topic_name, score, total):
    """Generate short, template-safe recommendations."""

    percentage = round((score / total) * 100) if total else 0

    prompt = f"""
You are ProcrastiNO, an AI study and career assistant.

Subject: {subject_name}
Topic: {topic_name}
Quiz Score: {score}/{total}
Percentage: {percentage}%

Give VERY SHORT and CLEAR recommendations.
Return ONLY valid JSON using EXACTLY this structure:

{{
    "career_relevance": "one short sentence about where this topic is useful in a career",
    "skills": ["one skill", "one skill"],
    "books": ["one book title", "one book title"],
    "youtube": ["one short YouTube learning recommendation", "one short YouTube learning recommendation"],
    "next_step": "one short sentence telling the student what to do next"
}}

Rules:
- No Markdown.
- No * or # symbols.
- No explanations or lessons.
- No long paragraphs.
- Maximum 2 items in skills, books, and youtube.
- Keep every item short and practical.
- Do not repeat the score.
"""

    fallback = {
        "career_relevance": f"Useful for building practical knowledge related to {topic_name}.",
        "skills": ["Problem solving", "Technical knowledge"],
        "books": [
            f"A standard textbook for {topic_name}",
            "Your recommended course textbook"
        ],
        "youtube": [
            f"{topic_name} tutorials",
            f"{topic_name} practice questions"
        ],
        "next_step": "Review the topic and attempt another quiz."
    }

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )

        text = response.text.strip()

        if text.startswith("```"):
            text = text.replace("```json", "", 1)
            text = text.replace("```", "")
            text = text.strip()

        data = json.loads(text)

        if not isinstance(data, dict):
            data = {}

        career_relevance = data.get("career_relevance", fallback["career_relevance"])
        skills = data.get("skills", fallback["skills"])
        books = data.get("books", fallback["books"])
        youtube = data.get("youtube", fallback["youtube"])
        next_step = data.get("next_step", fallback["next_step"])

        if not isinstance(skills, list):
            skills = [skills]
        if not isinstance(books, list):
            books = [books]
        if not isinstance(youtube, list):
            youtube = [youtube]

        return {
            "career_relevance": clean_ai_text(career_relevance),
            "skills": [clean_ai_text(x) for x in skills[:2]],
            "books": [clean_ai_text(x) for x in books[:2]],
            "youtube": [clean_ai_text(x) for x in youtube[:2]],
            "next_step": clean_ai_text(next_step)
        }

    except Exception:
        return fallback


# ============================================================
# AI RECOMMENDATIONS PAGE
# ============================================================

@app.route("/recommendations/<int:subject_id>/<int:topic_id>")
def recommendations(subject_id, topic_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, subject_name
        FROM subjects
        WHERE id = ? AND user_id = ?
    """, (subject_id, session["user_id"]))

    subject = cursor.fetchone()

    if not subject:
        conn.close()
        return "Subject not found!"

    cursor.execute("""
        SELECT id, topic_name
        FROM topics
        WHERE id = ? AND subject_id = ?
    """, (topic_id, subject_id))

    topic = cursor.fetchone()

    if not topic:
        conn.close()
        return "Topic not found!"

    cursor.execute("""
        SELECT score, total
        FROM quiz_results
        WHERE user_id = ?
        AND subject_id = ?
        AND topic_id = ?
        ORDER BY id DESC
        LIMIT 1
    """, (
        session["user_id"],
        subject_id,
        topic_id
    ))

    result = cursor.fetchone()
    conn.close()

    if not result:
        return "No quiz result found!"

    score = result[0]
    total = result[1]
    percentage = round((score / total) * 100) if total else 0

    ai_recommendations = generate_recommendations(
        subject[1],
        topic[1],
        score,
        total
    )

    return render_template(
        "recommendations.html",
        subject=subject,
        topic=topic,
        score=score,
        total=total,
        percentage=percentage,
        ai_recommendations=ai_recommendations
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()
    return redirect("/")


# ============================================================
# CAREER RECOMMENDATIONS
# ============================================================

@app.route("/career")
def career():

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT subjects.subject_name,
               AVG(CAST(quiz_results.score AS FLOAT) / quiz_results.total * 100)
        FROM quiz_results
        JOIN subjects
            ON quiz_results.subject_id = subjects.id
        WHERE quiz_results.user_id = ?
        GROUP BY subjects.id
        ORDER BY subjects.subject_name
    """, (session["user_id"],))

    subject_performance = cursor.fetchall()
    conn.close()

    if not subject_performance:
        recommendations = {
            "roles": [
                "Take a few quizzes to identify your strongest subjects.",
                "Use the Study Plan to build consistent skills."
            ],
            "skills": [
                "Problem solving",
                "Communication"
            ],
            "message": "Complete some quizzes to get more personalized career guidance."
        }
    else:
        performance_text = "\n".join(
            f"- {name}: {round(avg)}%"
            for name, avg in subject_performance
        )

        prompt = f"""
You are ProcrastiNO, an AI career and learning assistant.

Student's subject performance:
{performance_text}

Give a VERY SHORT career recommendation based on these subjects and scores.

Return ONLY valid JSON in this exact format:

{{
    "roles": ["one role", "one role"],
    "skills": ["one skill", "one skill"],
    "message": "one short recommendation"
}}

Rules:
- No Markdown.
- No * or # symbols.
- Maximum 2 roles.
- Maximum 2 skills.
- Keep every item short.
- Do not repeat the scores.
"""

        fallback = {
            "roles": [
                "Explore roles related to your strongest subject.",
                "Build projects to strengthen practical experience."
            ],
            "skills": [
                "Problem solving",
                "Practical project skills"
            ],
            "message": "Focus on your strongest subjects and build small projects around them."
        }

        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt
            )

            text = response.text.strip()

            if text.startswith("```"):
                text = text.replace("```json", "", 1)
                text = text.replace("```", "")
                text = text.strip()

            data = json.loads(text)

            roles = data.get("roles", fallback["roles"])
            skills = data.get("skills", fallback["skills"])
            message = data.get("message", fallback["message"])

            if not isinstance(roles, list):
                roles = [roles]

            if not isinstance(skills, list):
                skills = [skills]

            recommendations = {
                "roles": [clean_ai_text(x) for x in roles[:2]],
                "skills": [clean_ai_text(x) for x in skills[:2]],
                "message": clean_ai_text(message)
            }

        except Exception as e:
            print(f"Career recommendation generation failed: {e}")
            recommendations = fallback

    return render_template(
        "career.html",
        recommendations=recommendations,
        subject_performance=subject_performance
    )


# ============================================================
# STUDY PLAN
# ============================================================

@app.route("/study-plan", methods=["GET", "POST"])
def study_plan():

    if "user_id" not in session:
        return redirect("/login")

    plan = None
    subject = None
    performance_context = ""

    if request.method == "POST":

        subject = request.form.get("subject", "").strip()
        topics = request.form.get("topics", "").strip()
        exam_date = request.form.get("exam_date", "").strip()
        study_time = request.form.get("study_time", "").strip()

        try:
            exam = date.fromisoformat(exam_date)
            today = date.today()

            # Count only the days available BEFORE the exam.
            days_remaining = (exam - today).days - 1

            if days_remaining <= 0:
                return render_template(
                    "study_plan.html",
                    plan="No study days are available before this exam date. Please choose a later exam date.",
                    subject=subject
                )

            # ----------------------------------------------------
            # ADAPT THE PLAN USING THE STUDENT'S QUIZ PERFORMANCE
            # ----------------------------------------------------

            conn = sqlite3.connect("database.db")
            cursor = conn.cursor()

            cursor.execute("""
                SELECT AVG(
                    CAST(quiz_results.score AS FLOAT)
                    / quiz_results.total * 100
                )
                FROM quiz_results
                JOIN subjects
                    ON quiz_results.subject_id = subjects.id
                WHERE quiz_results.user_id = ?
                AND LOWER(subjects.subject_name) = LOWER(?)
            """, (session["user_id"], subject))

            subject_average = cursor.fetchone()[0]

            cursor.execute("""
                SELECT topics.topic_name,
                       quiz_results.score,
                       quiz_results.total
                FROM quiz_results
                JOIN topics
                    ON quiz_results.topic_id = topics.id
                JOIN subjects
                    ON quiz_results.subject_id = subjects.id
                WHERE quiz_results.user_id = ?
                AND LOWER(subjects.subject_name) = LOWER(?)
                ORDER BY quiz_results.id DESC
                LIMIT 5
            """, (session["user_id"], subject))

            recent_results = cursor.fetchall()
            conn.close()

            if subject_average is None:
                performance_context = (
                    "No previous quiz performance is available for this subject. "
                    "Create a balanced plan covering learning, practice, and revision."
                )

            elif subject_average < 60:
                performance_context = (
                    f"Previous quiz average: {round(subject_average)}%. "
                    "The student needs stronger revision. Give extra time to "
                    "weak areas, basic concepts, and practice questions."
                )

            elif subject_average < 80:
                performance_context = (
                    f"Previous quiz average: {round(subject_average)}%. "
                    "The student is progressing normally. Balance new learning "
                    "with revision and practice."
                )

            else:
                performance_context = (
                    f"Previous quiz average: {round(subject_average)}%. "
                    "The student is performing strongly. Include lighter revision "
                    "and some advanced or application-based practice."
                )

            # ----------------------------------------------------
            # SET STUDY PLAN LANGUAGE
            # ----------------------------------------------------

            subject_lower = subject.strip().casefold()

            if "hindi" in subject_lower or "हिंदी" in subject_lower:
                language_instruction = (
                    "Generate the ENTIRE study plan in Hindi (हिन्दी). "
                    "Use Hindi for Day labels, tasks, revision instructions, "
                    "and all explanations. Do not generate the plan in English."
                )
            elif "telugu" in subject_lower or "తెలుగు" in subject_lower:
                language_instruction = (
                    "Generate the ENTIRE study plan in Telugu (తెలుగు). "
                    "Use Telugu for Day labels, tasks, revision instructions, "
                    "and all explanations. Do not generate the plan in English."
                )
            else:
                language_instruction = "Generate the study plan in English."

            prompt = f"""
You are ProcrastiNO, an AI study planning assistant.

Create a short, practical and personalized study plan.

IMPORTANT LANGUAGE RULE:
{language_instruction}

Subject: {subject}
Topics: {topics}
Exam Date: {exam_date}
Available Study Time Per Day: {study_time} hours
Number of Study Days: {days_remaining}

Student performance:
{performance_context}

IMPORTANT RULES:

1. Create exactly {days_remaining} days.
2. DO NOT include the exam day.
3. Do not create an "Exam Day" section.
4. Use exactly 2 or 3 short bullet points for every day.
5. Keep every bullet short and practical.
6. Distribute the given topics across the available days.
7. Adapt revision difficulty according to the student's performance.
8. If performance is below 60%, prioritize basics, revision and practice.
9. If performance is 60–79%, balance learning, revision and practice.
10. If performance is 80% or above, include lighter revision and advanced practice.
11. Include final revision before the exam, but never include the exam day.
12. Do not add an introduction.
13. Do not add phases.
14. Do not add a conclusion.
15. Do not use Markdown headings such as # or ##.
16. Do not use long explanations.

Return ONLY in this format:

Day 1
- Short task
- Short task

Day 2
- Short task
- Short task

Continue until Day {days_remaining}.
"""
            # ----------------------------------------------------
            # GENERATE STUDY PLAN
            # Retry temporary Gemini errors and use a fallback model
            # only for the Study Plan.
            # ----------------------------------------------------

            response = None
            last_error = None

            models_to_try = [
                "gemini-3.6-flash",
                "gemini-2.5-flash"
            ]

            for model_name in models_to_try:
                for attempt in range(3):
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=prompt
                        )
                        break

                    except Exception as e:
                        last_error = e
                        error_text = str(e).upper()

                        temporary_error = (
                            "503" in error_text
                            or "UNAVAILABLE" in error_text
                            or "429" in error_text
                            or "RESOURCE_EXHAUSTED" in error_text
                        )

                        if not temporary_error:
                            # This model cannot be used for this request.
                            # Move to the next fallback model.
                            break

                        if attempt < 2:
                            time.sleep(2 ** attempt)

                if response is not None:
                    break

            if response is not None:
                plan = response.text.strip()

                if plan.startswith("```"):
                    plan = plan.replace("```text", "", 1)
                    plan = plan.replace("```", "")
                    plan = plan.strip()

            else:
                # ------------------------------------------------
                # LOCAL FALLBACK
                # ------------------------------------------------
                # If Gemini is temporarily unavailable, still give
                # the student a usable plan instead of an error.
                topic_list = [
                    item.strip()
                    for item in topics.split(",")
                    if item.strip()
                ]

                if not topic_list:
                    topic_list = ["the selected topic"]

                if "hindi" in subject_lower or "हिंदी" in subject_lower:
                    day_word = "दिन"
                    tasks = [
                        "मुख्य अवधारणाओं को पढ़ें और समझें",
                        "महत्वपूर्ण बिंदुओं के छोटे नोट्स बनाएं",
                        "अभ्यास प्रश्न हल करें",
                        "कमज़ोर भागों का दोबारा अभ्यास करें",
                        "सीखे हुए विषयों का त्वरित पुनरावलोकन करें",
                    ]
                elif "telugu" in subject_lower or "తెలుగు" in subject_lower:
                    day_word = "రోజు"
                    tasks = [
                        "ముఖ్యమైన భావాలను చదివి అర్థం చేసుకోండి",
                        "ముఖ్యమైన అంశాల చిన్న నోట్స్ తయారు చేయండి",
                        "అభ్యాస ప్రశ్నలను పరిష్కరించండి",
                        "బలహీనమైన అంశాలను మళ్లీ సాధన చేయండి",
                        "చదివిన విషయాలను త్వరగా పునశ్చరణ చేయండి",
                    ]
                else:
                    day_word = "Day"
                    tasks = [
                        "Study and understand the main concepts",
                        "Make short notes of important points",
                        "Solve practice questions",
                        "Revise weak areas and practise again",
                        "Do a quick revision of the topics studied",
                    ]

                plan_lines = []

                for day_index in range(days_remaining):
                    topic = topic_list[day_index % len(topic_list)]

                    plan_lines.append(f"{day_word} {day_index + 1}")

                    if day_index == days_remaining - 1:
                        plan_lines.append(f"- {tasks[4]}: {topic}")
                        plan_lines.append(f"- {tasks[3]}: {topic}")
                    else:
                        plan_lines.append(f"- {tasks[0]}: {topic}")
                        plan_lines.append(f"- {tasks[2]}: {topic}")

                plan = "\n".join(plan_lines)

            if plan.startswith("```"):
                plan = plan.replace("```text", "", 1)
                plan = plan.replace("```", "")
                plan = plan.strip()

        except Exception as e:
            print(f"Study plan generation failed: {type(e).__name__}: {e}")
            plan = (
                "Sorry! The study plan could not be generated right now. "
                "Please check your details and try again."
            )

    return render_template(
        "study_plan.html",
        plan=plan,
        subject=subject
    )

if __name__ == "__main__":
    init_db()
    app.run(debug=True)