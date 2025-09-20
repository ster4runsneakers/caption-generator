import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import google.generativeai as genai
from openai import OpenAI
import cloudinary
import cloudinary.uploader
import requests

# --- 1. Load Environment Variables FIRST ---
load_dotenv()

# --- 2. Create and Configure the App ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- 3. Initialize Extensions ---
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- 4. Define Database Model ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- Βοηθητικές Συναρτήσεις (Helpers) ---
def sanitize_for_prompt(text: str, max_length: int = 500) -> str:
    """Καθαρίζει και περιορίζει το κείμενο του χρήστη για χρήση σε prompt."""
    if not text:
        return ""
    return text.strip()[:max_length]

# --- Configure other clients (Cloudinary, AI) ---
cloudinary.config(cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"), api_key=os.getenv("CLOUDINARY_API_KEY"), api_secret=os.getenv("CLOUDINARY_API_SECRET"))
OPENAI_RESPONSES_MODEL = os.getenv("OPENAI_RESPONSES_MODEL", "gpt-4o-mini")
try:
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception as e:
    openai_client = None
try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    gemini_model = None

# --- Routes (Authentication, App, APIs) ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Λάθος όνομα χρήστη ή κωδικός')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            flash('Αυτό το όνομα χρήστη υπάρχει ήδη')
        else:
            new_user = User(username=username)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload-image', methods=['POST'])
@login_required
def upload_image():
    if 'file' not in request.files: return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"error": "No selected file"}), 400
    if file:
        try:
            upload_result = cloudinary.uploader.upload(file)
            return jsonify({"image_url": upload_result.get('secure_url')})
        except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/generate-caption', methods=['POST'])
@login_required
def generate_caption():
    data = request.get_json()
    if not data or 'topic' not in data: return jsonify({"error": "Topic is required"}), 400
    # Sanitize free-text inputs to mitigate prompt injection risks
    topic = sanitize_for_prompt(data.get('topic'))
    keywords = sanitize_for_prompt(data.get('keywords'))
    brand_voice = sanitize_for_prompt(data.get('brand_voice', ''))

    # Get other parameters (assumed to be from a fixed set of choices)
    platform = data.get('platform')
    tone = data.get('tone')
    content_type = data.get('contentType')
    language = data.get('language')
    model_choice = data.get('model_choice', 'openai')
    content_map = {'Caption': 'a full caption (including a hook, body, and CTA)','Hook': 'only a compelling hook','CTA': 'only a strong call-to-action (CTA)','Hashtags': 'a list of 10 relevant hashtags'}
    requested_content = content_map.get(content_type, 'a full caption')
    prompt = ""
    if brand_voice: prompt += f"SPECIAL INSTRUCTION: Adhere strictly to the following brand voice: '{brand_voice}'.\n\n"
    prompt += f"""Generate 3 distinct options for {requested_content} for a {platform} post.
    The main topic is: '{topic}'.
    The desired tone is: {tone}.
    Keywords to include: {keywords if keywords else 'None'}.
    The output language must be strictly {language}.
    Structure the output as a numbered list."""
    generated_text = ""
    try:
        if model_choice == 'gemini':
            if not gemini_model: raise ConnectionError("Gemini client not initialized.")
            response = gemini_model.generate_content(prompt)
            generated_text = response.text
        else:
            if not openai_client: raise ConnectionError("OpenAI client not initialized.")
            # Generate captions via the OpenAI Responses API using the gpt-4o-mini model (configurable via env).
            response = openai_client.responses.create(
                model=OPENAI_RESPONSES_MODEL,
                input=[{"role": "user", "content": prompt}]
            )
            generated_text = getattr(response, "output_text", "")
            if not generated_text:
                segments = []
                for item in getattr(response, "output", []) or []:
                    if getattr(item, "type", "") == "output_text":
                        segments.append(getattr(item, "text", ""))
                generated_text = "".join(segments)
        return jsonify({"caption": generated_text.strip()})
    except Exception as e:
        print(f"Error during AI generation with {model_choice}: {e}")
        return jsonify({"error": f"An error occurred with the {model_choice} API."}), 500

@app.route('/generate-image', methods=['POST'])
@login_required
def generate_image():
    if not openai_client: return jsonify({"error": "OpenAI client is not configured."}), 500
    data = request.get_json()
    prompt = data.get('prompt')
    style = data.get('style', 'photorealistic')
    if not prompt: return jsonify({"error": "Image prompt is required"}), 400
    full_prompt = f"{prompt}, in a {style} style."
    try:
        response = openai_client.images.generate(model="dall-e-3", prompt=full_prompt, size="1024x1024", quality="standard", n=1)
        return jsonify({"image_url": response.data[0].url})
    except Exception as e:
        return jsonify({"error": "Failed to generate image."}), 500

@app.route('/analyze-image', methods=['POST'])
@login_required
def analyze_image():
    if not gemini_model: return jsonify({"error": "Gemini client not initialized."}), 500
    data = request.get_json()
    image_url = data.get('image_url')
    if not image_url: return jsonify({"error": "Image URL is required"}), 400
    try:
        image_response = requests.get(image_url, stream=True)
        image_response.raise_for_status()
        image_parts = [{"mime_type": image_response.headers['Content-Type'],"data": image_response.content}]
        prompt_parts = [image_parts[0], "\nDescribe this image in detail for a social media post. Be descriptive and engaging. The description should be in Greek."]
        response = gemini_model.generate_content(prompt_parts)
        return jsonify({"description": response.text})
    except Exception as e:
        return jsonify({"error": "Failed to analyze image."}), 500

# --- Create database tables and run app ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)