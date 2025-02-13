from flask import Flask, request, render_template, jsonify
import sqlite3
import ollama
import pyttsx3
import base64
import logging

from flask_cors import CORS  # ✅ Allows frontend to talk to backend

app = Flask(__name__)
CORS(app)  # ✅ Enable CORS for API calls

DATABASE = 'student_chat.db'

# Setup logging
logging.basicConfig(level=logging.INFO)

def init_db():
    """Initialize SQLite database and ensure correct schema."""
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        
        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS student_chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_input TEXT,
                llama_response TEXT
            )
        """)

        # Check if 'quiz_questions' column exists
        cursor.execute("PRAGMA table_info(student_chats);")
        columns = [col[1] for col in cursor.fetchall()]
        
        if "quiz_questions" not in columns:
            cursor.execute("ALTER TABLE student_chats ADD COLUMN quiz_questions TEXT;")
            print("✅ Column 'quiz_questions' added to database.")

        conn.commit()

def get_voice_options():
    """Retrieve available voices from pyttsx3"""
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    return [{'id': i, 'name': voice.name} for i, voice in enumerate(voices)]

@app.route('/')
def index():
    """Render the HTML page"""
    voices = get_voice_options()
    return render_template('main1.1.html', voices=voices)

@app.route('/chat', methods=['POST'])
def chat():
    """Handle chat messages"""
    try:
        user_input = request.json.get('content', '')
        selected_voice = int(request.json.get('voice', 0))
        speech_rate = int(request.json.get('rate', 150))
        speech_volume = float(request.json.get('volume', 1.0))

        # Query Ollama API
        response = ollama.chat(model='gemma2:2b', messages=[{'role': 'user', 'content': user_input}])
        message_content = response['message']['content']

        # Convert text to speech
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        engine.setProperty('voice', voices[selected_voice].id)
        engine.setProperty('rate', speech_rate)
        engine.setProperty('volume', speech_volume)

        engine.save_to_file(message_content, "temp.wav")
        engine.runAndWait()

        with open("temp.wav", "rb") as audio_file:
            audio_data = audio_file.read()

        audio_b64 = base64.b64encode(audio_data).decode('utf-8')

        # Store in database
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO student_chats (user_input, llama_response) VALUES (?, ?)",
                           (user_input, message_content))
            conn.commit()

        return jsonify({"message": message_content, "audio": audio_b64})

    except Exception as e:
        logging.error(f"Chat error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/quiz', methods=['POST'])
def generate_quiz():
    """Generate 10 quiz questions based on user input"""
    try:
        topic = request.json.get('topic', '')

        if not topic:
            return jsonify({"error": "Topic is required"}), 400

        quiz_prompt = f"""
        You are a quiz generator. Create exactly 10 quiz questions about "{topic}". 
        Provide them as a dot list. Avoid any extra text.
        """

        response = ollama.chat(model='gemma2:2b', messages=[{'role': 'user', 'content': quiz_prompt}])

        logging.info(f"Ollama Response: {response}")

        if 'message' not in response or 'content' not in response['message']:
            return jsonify({"error": "Invalid response from Ollama"}), 500

        quiz_questions = response['message']['content'].split("\n")

        # Ensure at least 10 questions are generated
        if len(quiz_questions) < 10:
            return jsonify({"error": "Failed to generate quiz. Try a different topic."}), 500

        # Save to database
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO student_chats (user_input, quiz_questions) VALUES (?, ?)",
                           (topic, '\n'.join(quiz_questions)))
            conn.commit()

        return jsonify({"quiz": quiz_questions})

    except Exception as e:
        logging.error(f"Quiz Generation Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/view-data', methods=['GET'])
def view_data():
    """View stored chat & quiz data"""
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM student_chats")
            data = cursor.fetchall()

        return jsonify({"stored_data": data})

    except Exception as e:
        logging.error(f"Database Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
