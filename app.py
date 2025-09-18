import os
import google.generativeai as genai
from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# --- Initialize AI clients ---
try:
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception as e:
    openai_client = None

try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    gemini_model = None

@app.route('/')
def index():
    return render_template('index.html')

# --- Endpoint for Text Generation ---
@app.route('/generate-caption', methods=['POST'])
def generate_caption():
    # ... (this function remains exactly the same as before)
    data = request.get_json()
    if not data or 'topic' not in data:
        return jsonify({"error": "Topic is required"}), 400
    topic = data.get('topic')
    platform = data.get('platform')
    tone = data.get('tone')
    content_type = data.get('contentType')
    language = data.get('language')
    keywords = data.get('keywords')
    model_choice = data.get('model_choice', 'openai')
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
        if model_choice == 'gemini':
            if not gemini_model: raise ConnectionError("Gemini client not initialized.")
            response = gemini_model.generate_content(prompt)
            generated_text = response.text
        else:
            if not openai_client: raise ConnectionError("OpenAI client not initialized.")
            chat_completion = openai_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}], model="gpt-3.5-turbo",
            )
            generated_text = chat_completion.choices[0].message.content
        return jsonify({"caption": generated_text.strip()})
    except Exception as e:
        return jsonify({"error": f"An error occurred with the {model_choice} API."}), 500

# --- ## NEW ENDPOINT FOR IMAGE GENERATION ## ---
@app.route('/generate-image', methods=['POST'])
def generate_image():
    if not openai_client:
        return jsonify({"error": "OpenAI client is not configured for image generation."}), 500

    data = request.get_json()
    prompt = data.get('prompt')
    style = data.get('style', 'photorealistic') # Default style

    if not prompt:
        return jsonify({"error": "Image prompt is required"}), 400

    full_prompt = f"{prompt}, in a {style} style."

    try:
        response = openai_client.images.generate(
            model="dall-e-3",
            prompt=full_prompt,
            size="1024x1024", # Standard size for DALL-E 3
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url
        return jsonify({"image_url": image_url})
    except Exception as e:
        print(f"Error generating image with DALL-E: {e}")
        return jsonify({"error": "Failed to generate image. The prompt may have been rejected."}), 500

if __name__ == '__main__':
    app.run(debug=True)