import os
from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from dotenv import load_dotenv
from flask_cors import CORS

load_dotenv()
app = Flask(__name__)
CORS(app) 

try:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception as e:
    print(f"Error initializing OpenAI client: {e}")
    client = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate-caption', methods=['POST'])
def generate_caption():
    if not client:
        return jsonify({"error": "OpenAI client not initialized."}), 500
        
    data = request.get_json()
    if not data or 'topic' not in data:
        return jsonify({"error": "Topic is required"}), 400

    topic = data.get('topic')
    platform = data.get('platform', 'Instagram')
    tone = data.get('tone', 'Friendly')
    content_type = data.get('contentType', 'Caption')
    language = data.get('language', 'Greek')
    keywords = data.get('keywords', '') # Get keywords

    # Build the main instruction based on content type
    content_map = {
        'Caption': 'a full caption (including a hook, body, and CTA)',
        'Hook': 'only a compelling hook (the opening line)',
        'CTA': 'only a strong call-to-action (CTA)',
        'Hashtags': 'a list of 10 relevant and trending hashtags'
    }
    requested_content = content_map.get(content_type, 'a full caption')

    # Construct the final prompt
    prompt = f"""
    Generate 3 distinct and creative options for {requested_content} for a {platform} post.
    The main topic is: '{topic}'.
    The desired tone is: {tone}.
    """
    
    if keywords:
        prompt += f"\nIt is crucial to include the following keywords: {keywords}."

    prompt += f"\nIMPORTANT: The output language must be strictly {language}."
    prompt += "\nStructure the output as a numbered list."

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="gpt-3.5-turbo",
        )
        generated_text = chat_completion.choices[0].message.content.strip()
        return jsonify({"caption": generated_text})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)