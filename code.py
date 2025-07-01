import os
import docx2txt
import re
import PyPDF2
import streamlit as st
import pymysql
import hashlib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import MinMaxScaler

UPLOAD_FOLDER = 'uploads/'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ✅ Initialize Streamlit session state
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'register_mode' not in st.session_state:
    st.session_state.register_mode = False

# ✅ MySQL Connection
def create_connection():
    return pymysql.connect(
        host='localhost',
        port=3306,
        user="root",
        password="Neha@29052001",
        database="RESUME"
    )


# Initialize database and create table if not exists
def initialize_database():
    conn = create_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("CREATE DATABASE IF NOT EXISTS RESUME")
        cursor.execute("USE RESUME")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL
            )
        """)
        conn.commit()
    except pymysql.MySQLError as err:
        st.error(f"Error initializing database: {err}")
    finally:
        cursor.close()
        conn.close()

# User management functions
def add_user(username, password):
    hashed = hashlib.sha256(password.encode('utf-8')).hexdigest()
    conn = create_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO user (username, password) VALUES (%s, %s)", (username, hashed))
        conn.commit()
        st.success("User registered successfully!")
        st.session_state.logged_in = True 
    except pymysql.MySQLError as err:
        st.error(f"Error: {err}")
    finally:
        cursor.close()
        conn.close()

# ✅ Extract text from resumes
def extract_text(file_path):
    if file_path.endswith('.pdf'):
        text = ""
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text += page.extract_text() or ""
        return text.strip()
    elif file_path.endswith('.docx'):
        return docx2txt.process(file_path).strip()
    elif file_path.endswith('.txt'):
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read().strip()
    return ""

# ✅ Validate if a file is a resume
def is_resume_file(file_path):
    text = extract_text(file_path)
    if len(text) < 100:
        return False
    resume_keywords = ["experience", "education", "skills", "projects", "certifications","professional", "portfolio", "career",
     "accomplishments", "achievements", "summary", "contact", "references","objective"]
    return sum(1 for keyword in resume_keywords if keyword.lower() in text.lower()) >= 4

# ✅ Generate suggestions based on job role
def generate_suggestions(job_role, resume_text):
    suggestions = []
    job_role = job_role.lower()
    if "data analyst" in job_role or "data scientist" in job_role:
        if "python" not in resume_text.lower():
            suggestions.append("🔹 Add Python skills, essential for data analysis.")
        if "sql" not in resume_text.lower():
            suggestions.append("🔹 Include SQL experience for data querying.")
    elif "java developer" in job_role or "software developer" in job_role:
        if "java" not in resume_text.lower():
            suggestions.append("🔹 Add Java experience, a core requirement.")
        if "spring boot" not in resume_text.lower():
            suggestions.append("🔹 Mention Spring Boot for enterprise apps.")
    elif "web developer" in job_role:
        if "html" not in resume_text.lower() or "css" not in resume_text.lower():
            suggestions.append("🔹 Highlight HTML/CSS skills for UI development.")
    if not suggestions:
        suggestions.append("✅ Your resume is relevant but could be improved with more details on projects.")
    return suggestions

def detect_fake_university(text):
    fake_universities = [
        "Rochville University", "Almeda University", "Axact University",
        "Corllins University", "Kings Lake University"
    ]
    return any(uni.lower() in text.lower() for uni in fake_universities)

def detect_fake_company(text):
    fake_companies = [
        "Apex Global Solutions", "Dream Tech Solutions", "Innovative Dynamics Ltd",
        "Future Vision Technologies", "Skyline Infosys"
    ]
    return any(company.lower() in text.lower() for company in fake_companies)

def detect_unrealistic_experience(text):
    match = re.findall(r'(\d{1,2})\s*years', text.lower())
    return any(int(years) > 40 or int(years) < 0 for years in map(int, match))

# ✅ Resume matching function
def match_resumes(job_description, resume_files, job_role):
    resumes, valid_files, resume_texts = [], [], []
    for resume_file in resume_files:
        file_path = os.path.join(UPLOAD_FOLDER, resume_file.name)
        with open(file_path, 'wb') as f:
            f.write(resume_file.getbuffer())
        if not is_resume_file(file_path):
            st.warning(f"⚠ Skipping {resume_file.name} - Not a valid resume file.")
            continue
        resume_text = extract_text(file_path)
        resumes.append(resume_text)
        valid_files.append(resume_file)
        resume_texts.append(resume_text)
    if not resumes:
        return [], [], [], []
    vectorizer = TfidfVectorizer(ngram_range=(1, 3), stop_words='english', max_features=5000)
    tfidf_matrix = vectorizer.fit_transform([job_description] + resumes)
    similarity_matrix = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]
    scaler = MinMaxScaler(feature_range=(60, 100))
    scores_scaled = scaler.fit_transform(similarity_matrix.reshape(-1, 1)).flatten()
    top_indices = scores_scaled.argsort()[-5:][::-1]
    top_resumes = [valid_files[i].name for i in top_indices if i < len(valid_files)]
    scores = [round(scores_scaled[i], 2) for i in top_indices if i < len(scores_scaled)]
    fake_checks = []
    suggestions = []

    fake_checks = []
    suggestions = []

    for i in top_indices:
        if i >= len(resume_texts):
            fake_checks.append("❌ Unable to verify fake details.")
            suggestions.append(["❌ Unable to analyze suggestions due to indexing error."])
        else:
            text = resume_texts[i]
            fake_flag = False
            if detect_fake_university(text):
                fake_checks.append("⚠ Fake University Detected")
                fake_flag = True
            elif detect_fake_company(text):
                fake_checks.append("⚠ Fake Company Detected")
                fake_flag = True
            elif detect_unrealistic_experience(text):
                fake_checks.append("⚠ Unrealistic Experience Detected")
                fake_flag = True
            if not fake_flag:
                fake_checks.append("✅ Genuine")

            if scores_scaled[i] < 70:
                suggestions.append(generate_suggestions(job_role, text))
            else:
                suggestions.append(["✅ Good match! No major changes needed."])


    return top_resumes, scores, fake_checks, suggestions

# ✅ Streamlit UI
st.title("AI Resume Analyzer")

if not st.session_state.logged_in:
    if st.session_state.register_mode:
        st.subheader("Register")
        new_username = st.text_input("Choose a username")
        new_password = st.text_input("Choose a password", type='password')
        confirm_password = st.text_input("Confirm password", type='password')

        if st.button("Register"):
            if not new_username or not new_password or not confirm_password:
                st.error("❌ Please fill all the fields.")
            elif new_password != confirm_password:
                st.error("❌ Passwords do not match.")
            else:
                conn = create_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM user WHERE username = %s", (new_username,))
                if cursor.fetchone():
                    st.error("⚠ Username already exists. Try another one.")
                else:
                    hashed_pw = hashlib.sha256(new_password.encode('utf-8')).hexdigest()
                    cursor.execute("INSERT INTO user (username, password) VALUES (%s, %s)", (new_username, hashed_pw))
                    conn.commit()
                    st.success("✅ Registered successfully! You can now login.")
                    st.session_state.register_mode = False
                cursor.close()
                conn.close()
        if st.button("Back to Login"):
            st.session_state.register_mode = False

    else:
        st.subheader("Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type='password')

        if st.button("Login"):
            conn = create_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT password FROM user WHERE username=%s", (username,))
            result = cursor.fetchone()
            if result and hashlib.sha256(password.encode('utf-8')).hexdigest() == result[0]:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.success("✅ Logged in successfully!")
            else:
                st.error("❌ Invalid username or password.")
            cursor.close()
            conn.close()

        if st.button("Register"):
            st.session_state.register_mode = True

else:
    st.subheader("Enter Job Description")
    job_description = st.text_area("Job Description")
    job_role = st.text_input("Enter Job Role")
    resume_files = st.file_uploader("Upload Resumes", type=['pdf', 'docx', 'txt'], accept_multiple_files=True)

    if st.button("Match Resumes"):
        top_resumes, scores, fake_checks,suggestions = match_resumes(job_description, resume_files, job_role)
        if not top_resumes:
            st.error("❌ No valid resumes matched the job description.")
        else:
            for i, (resume, score, fake_status, suggestion_list) in enumerate(zip(top_resumes, scores, fake_checks, suggestions)):
                st.write(f"📄 {resume} \n🔍 Score: {score}% \n⚠ Fake Check: {fake_status}")
                if score < 70:
                    st.warning("🔍 Suggestions for Improvement:")
                    for suggestion in suggestion_list:
                        st.write(suggestion)

    if st.button("Logout"):
        st.session_state.logged_in = False
        st.success("Logged out successfully.")
