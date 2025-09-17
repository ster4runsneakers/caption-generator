import os
from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from dotenv import load_dotenv
from flask_cors import CORS

# Load environment variables from .env file
load_dotenv()

# Create the Flask application
app = Flask(__name__)
CORS(app) 

# Initialize the OpenAI client
try:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception as e:
    print(f"Error initializing OpenAI client: {e}")
    client = None

# Route to serve the main HTML page
@app.route('/')
def index():
    return render_template('index.html')

# API endpoint for generating captions
@app.route('/generate-caption', methods=['POST'])
def generate_caption():
    if not client:
        return jsonify({"error": "OpenAI client not initialized. Check your API key."}), 500
        
    data = request.get_json()

    if not data or 'topic' not in data:
        return jsonify({"error": "Topic is required"}), 400

    topic = data.get('topic')
    platform = data.get('platform', 'Instagram')
    tone = data.get('tone', 'Friendly')

    # New, smarter prompt
    prompt = f"""
    Generate 3 distinct, creative, and engaging captions for a {platform} post.
    The topic is: '{topic}'.
    The desired tone is: {tone}.
    
    Please structure the output clearly, for example:
    1. [First caption here with relevant hashtags]
    2. [Second caption here with relevant hashtags]
    3. [Third caption here with relevant hashtags]
    """

    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="gpt-3.5-turbo",
        )

        generated_text = chat_completion.choices[0].message.content.strip()
        return jsonify({"caption": generated_text})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Start the server when the script is run
if __name__ == '__main__':
    app.run(debug=True)