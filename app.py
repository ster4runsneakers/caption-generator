import os
import logging
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import requests
import cloudinary
import cloudinary.uploader
import google.generativeai as genai
from openai import OpenAI

# ---------------- Boot ----------------
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'change-me-in-prod')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ---------------- Models ----------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- JSON 401 για AJAX αντί για HTML redirect ---
@login_manager.unauthorized_handler
def unauthorized():
    accepts_json = 'application/json' in (request.headers.get('Accept') or '')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if accepts_json or is_ajax:
        return jsonify({"error": "Unauthorized"}), 401
    return redirect(url_for('login'))

# ---------------- External clients ----------------
# Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)

# OpenAI
try:
    openai_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    openai_client = OpenAI(api_key=openai_key) if openai_key else None
    if not openai_client:
        logger.info("OPENAI_API_KEY missing; OpenAI features will be limited.")
except Exception as e:
    logger.warning(f"OpenAI init failed: {e}")
    openai_client = None

# Gemini (optional)
try:
    gem_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if gem_key:
        genai.configure(api_key=gem_key)
        gemini_model = genai.GenerativeModel('gemini-1.5-flash')
    else:
        gemini_model = None
        logger.info("GEMINI_API_KEY missing; image analysis will use OpenAI fallback.")
except Exception as e:
    logger.warning(f"Gemini init failed: {e}")
    gemini_model = None

# ---------------- Routes: Auth ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Λάθος όνομα χρήστη ή κωδικός', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or not password:
            flash('Συμπλήρωσε όνομα χρήστη και κωδικό', 'error')
            return render_template('register.html')
        if User.query.filter_by(username=username).first():
            flash('Αυτό το όνομα χρήστη υπάρχει ήδη', 'error')
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

# ---------------- Routes: App ----------------
@app.route('/')
def index():
    # Το index.html σου παραμένει όπως το έφτιαξες/σου έστειλα.
    return render_template('index.html')

@app.route('/upload-image', methods=['POST'])
@login_required
def upload_image():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    try:
        upload_result = cloudinary.uploader.upload(file)
        return jsonify({"image_url": upload_result.get('secure_url')})
    except Exception as e:
        logger.exception("Cloudinary upload failed")
        return jsonify({"error": str(e)}), 500

@app.route('/generate-caption', methods=['POST'])
@login_required
def generate_caption():
    data = request.get_json(silent=True) or {}
    if 'topic' not in data:
        return jsonify({"error": "Topic is required"}), 400

    topic = data.get('topic', '')
    platform = data.get('platform', 'social')
    tone = data.get('tone', 'neutral')
    content_type = data.get('contentType', 'Caption')
    language = data.get('language', 'Greek')
    keywords = data.get('keywords', '')
    model_choice = data.get('model_choice', 'openai')
    brand_voice = data.get('brand_voice', '')

    content_map = {
        'Caption': 'a full caption (including a hook, body, and CTA)',
        'Hook': 'only a compelling hook',
        'CTA': 'only a strong call-to-action (CTA)',
        'Hashtags': 'a list of 10 relevant hashtags'
    }
    requested_content = content_map.get(content_type, 'a full caption')

    prompt = ""
    if brand_voice:
        prompt += f"SPECIAL INSTRUCTION: Adhere strictly to the following brand voice: '{brand_voice}'.\n\n"
    prompt += (
        f"Generate 3 distinct options for {requested_content} for a {platform} post.\n"
        f"The main topic is: '{topic}'.\n"
        f"The desired tone is: {tone}.\n"
        f"Keywords to include: {keywords if keywords else 'None'}.\n"
        f"The output language must be strictly {language}.\n"
        f"Structure the output as a numbered list."
    )

    try:
        if model_choice == 'gemini':
            if not gemini_model:
                raise ConnectionError("Gemini client not initialized.")
            response = gemini_model.generate_content(prompt)
            generated_text = (response.text or "").strip()
        else:
            if not openai_client:
                raise ConnectionError("OpenAI client not initialized.")
            chat = openai_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="gpt-4o-mini"
            )
            generated_text = (chat.choices[0].message.content or "").strip()

        if not generated_text:
            return jsonify({"error": "Empty response from the AI model."}), 502

        return jsonify({"caption": generated_text})
    except Exception as e:
        logger.exception(f"AI generation error via {model_choice}")
        return jsonify({"error": f"An error occurred with the {model_choice} API."}), 500

@app.route('/generate-image', methods=['POST'])
@login_required
def generate_image():
    if not openai_client:
        return jsonify({"error": "OpenAI client is not configured."}), 500
    data = request.get_json(silent=True) or {}
    prompt = data.get('prompt', '').strip()
    style = data.get('style', 'photorealistic')
    if not prompt:
        return jsonify({"error": "Image prompt is required"}), 400
    full_prompt = f"{prompt}, in a {style} style."
    try:
        response = openai_client.images.generate(
            model="dall-e-3",
            prompt=full_prompt,
            size="1024x1024",
            quality="standard",
            n=1
        )
        return jsonify({"image_url": response.data[0].url})
    except Exception as e:
        logger.exception("DALL-E image generation failed")
        return jsonify({"error": "Failed to generate image."}), 500

@app.route('/analyze-image', methods=['POST'])
@login_required
def analyze_image():
    data = request.get_json(silent=True) or {}
    image_url = (data.get('image_url') or '').strip()
    if not image_url:
        return jsonify({"error": "Image URL is required"}), 400

    # 1) Try Gemini (if configured)
    if gemini_model:
        try:
            image_response = requests.get(image_url, stream=True, timeout=20)
            image_response.raise_for_status()
            image_parts = [{
                "mime_type": image_response.headers.get('Content-Type', 'image/jpeg'),
                "data": image_response.content
            }]
            prompt_parts = [
                image_parts[0],
                "\nDescribe this image in detail for a social media post. "
                "Be descriptive and engaging. The description should be in Greek."
            ]
            response = gemini_model.generate_content(prompt_parts)
            text = (getattr(response, "text", "") or "").strip()
            if text:
                return jsonify({"description": text})
            # fall through if empty
        except Exception:
            logger.exception("Gemini image analysis failed, falling back to OpenAI")

    # 2) Fallback: OpenAI Vision (GPT-4o mini)
    if not openai_client:
        return jsonify({"error": "No available AI provider for image analysis."}), 500
    try:
        chat = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text":
                        "Describe this image in detail for a social media post. "
                        "Be descriptive and engaging. The description should be in Greek."
                    },
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            }]
        )
        text = (chat.choices[0].message.content or "").strip()
        if not text:
            return jsonify({"error": "Empty response from the AI model."}), 502
        return jsonify({"description": text})
    except Exception:
        logger.exception("OpenAI image analysis failed")
        return jsonify({"error": "Failed to analyze image."}), 500

# Healthcheck
@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

# ---------------- Main ----------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
