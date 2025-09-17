import os
from flask import Flask, request, jsonify
from openai import OpenAI
from dotenv import load_dotenv
from flask_cors import CORS # <-- 1. ΕΙΣΑΓΩΓΗ ΤΗΣ ΒΙΒΛΙΟΘΗΚΗΣ CORS

# Φορτώνει τις μεταβλητές από το αρχείο .env (το API key μας)
load_dotenv()

# Δημιουργία της Flask εφαρμογής
app = Flask(__name__)

# <-- 2. ΕΝΕΡΓΟΠΟΙΗΣΗ ΤΟΥ CORS ΓΙΑ ΟΛΗ ΤΗΝ ΕΦΑΡΜΟΓΗ
CORS(app) 

# Δημιουργία ενός client για την επικοινωνία με το OpenAI API
try:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception as e:
    print(f"Error initializing OpenAI client: {e}")
    client = None

# Ορίζουμε το endpoint μας για τη δημιουργία caption.
@app.route('/generate-caption', methods=['POST'])
def generate_caption():
    if not client:
        return jsonify({"error": "OpenAI client not initialized. Check your API key."}), 500
        
    # Παίρνουμε τα δεδομένα που έστειλε το frontend (σε μορφή JSON)
    data = request.get_json()

    # Ελέγχουμε αν μας έστειλε το θέμα (topic)
    if not data or 'topic' not in data:
        return jsonify({"error": "Topic is required"}), 400

    topic = data.get('topic')
    platform = data.get('platform', 'Instagram')

    # "Χτίζουμε" την ερώτηση (prompt) προς το ChatGPT
    prompt = f"Create a captivating and short {platform} caption for a post about '{topic}'. Include relevant hashtags."

    try:
        # Καλούμε το API του ChatGPT
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="gpt-3.5-turbo",
        )

        # Παίρνουμε την απάντηση
        generated_text = chat_completion.choices[0].message.content.strip()

        # Επιστρέφουμε την απάντηση σε μορφή JSON
        return jsonify({"caption": generated_text})

    except Exception as e:
        # Αν κάτι πάει στραβά με το API call, επιστρέφουμε ένα μήνυμα λάθους
        return jsonify({"error": str(e)}), 500

# Μια απλή διαδρομή για να ελέγξουμε αν ο server μας τρέχει
@app.route('/')
def index():
    return "Caption Generator API is running!"


# Ξεκινάει τον server όταν εκτελούμε το αρχείο με 'python app.py'
if __name__ == '__main__':
    app.run(debug=True)