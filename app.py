import os
import google.generativeai as genai
from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# --- Initialize both AI clients ---
# OpenAI Client
try:
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception as e:
    print(f"Error initializing OpenAI client: {e}")
    openai_client = None

# Google Gemini Client
try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    print(f"Error initializing Gemini client: {e}")
    gemini_model = None


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate-caption', methods=['POST'])
def generate_caption():
    data = request.get_json()
    if not data or 'topic' not in data:
        return jsonify({"error": "Topic is required"}), 400

    # Get all parameters from the frontend
    topic = data.get('topic')
    platform = data.get('platform')
    tone = data.get('tone')
    content_type = data.get('contentType')
    language = data.get('language')
    keywords = data.get('keywords')
    model_choice = data.get('model_choice', 'openai') # Default to openai if not provided

    # --- Build the prompt (it's the same for both models) ---
    content_map = {
        'Caption': 'a full caption (including a hook, body, and CTA)',
        'Hook': 'only a compelling hook',
        'CTA': 'only a strong call-to-action (CTA)',
        'Hashtags': 'a list of 10 relevant hashtags'
    }
    requested_content = content_map.get(content_type, 'a full caption')
    
    prompt = f"""
    Generate 3 distinct options for {requested_content} for a {platform} post.
    The main topic is: '{topic}'.
    The desired tone is: {tone}.
    Keywords to include: {keywords if keywords else 'None'}.
    The output language must be strictly {language}.
    Structure the output as a numbered list.
    """

    generated_text = ""
    try:
        # --- Use an if-statement to choose the AI model ---
        if model_choice == 'gemini':
            if not gemini_model:
                raise ConnectionError("Gemini client not initialized.")
            response = gemini_model.generate_content(prompt)
            generated_text = response.text
        else: # Default to OpenAI
            if not openai_client:
                raise ConnectionError("OpenAI client not initialized.")
            chat_completion = openai_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="gpt-3.5-turbo",
            )
            generated_text = chat_completion.choices[0].message.content

        return jsonify({"caption": generated_text.strip()})

    except Exception as e:
        print(f"Error during AI generation with {model_choice}: {e}")
        return jsonify({"error": f"An error occurred with the {model_choice} API. Please try again."}), 500

if __name__ == '__main__':
    app.run(debug=True)