import os
from werkzeug.security import check_password_hash
import random
import json
import requests
from flask import Flask, render_template, request, redirect, url_for, session, Response, jsonify
import database as db
import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_db()

def generate_captcha():
    num1 = random.randint(1, 9)
    num2 = random.randint(1, 9)
    session['captcha_text'] = str(num1 + num2)
    return f"Сколько будет {num1} + {num2}?"

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('auth'))
    chats = db.get_user_chats(session['user_id'])
    return render_template('index.html', username=session['username'], chats=chats)

@app.route('/auth', methods=['GET', 'POST'])
def auth():
    error = None
    
    if request.method == 'POST':
        action = request.form.get('action')
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        captcha_input = request.form.get('captcha', '').strip()
        
        if captcha_input != session.get('captcha_text'):
            error = "❌ Неверный ответ на капчу! Вы бот?"
            captcha_question = generate_captcha()
            return render_template('auth.html', captcha_question=captcha_question, error=error)
            
        if action == 'register':
            if len(password) < 6:
                error = "❌ Пароль слишком короткий (минимум 6 символов)!"
            elif db.register_user(username, password):
                user = db.check_user(username, password)
                session['user_id'] = user['id']
                session['username'] = user['username']
                return redirect(url_for('index'))
            else:
                error = "❌ Такое имя пользователя уже занято!"
                
        elif action == 'login':
            user = db.check_user(username, password)
            if user:
                session['user_id'] = user['id']
                session['username'] = user['username']
                return redirect(url_for('index'))
            else:
                error = "❌ Неверное имя пользователя или пароль!"

        captcha_question = generate_captcha()
        return render_template('auth.html', captcha_question=captcha_question, error=error)

    captcha_question = generate_captcha()
    return render_template('auth.html', captcha_question=captcha_question, error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth'))

@app.route('/api/chat/new', methods=['POST'])
def api_new_chat():
    if 'user_id' not in session: return jsonify({"error": "Unauthorized"}), 401
    chat_id = db.create_chat(session['user_id'])
    return jsonify({"chat_id": chat_id})

@app.route('/api/chat/<int:chat_id>/messages')
def api_get_messages(chat_id):
    if 'user_id' not in session: return jsonify({"error": "Unauthorized"}), 401
    rows = db.get_chat_messages(chat_id)
    messages = []
    for r in rows:
        messages.append({
            "role": r['role'],
            "content": r['content'],
            "image_path": None # Картинки отключены
        })
    return jsonify({"messages": messages})

@app.route('/api/chat/stream', methods=['POST'])
def api_stream_chat():
    if 'user_id' not in session: return "Unauthorized", 401
    
    chat_id = request.form.get('chat_id')
    user_message = request.form.get('message', '').strip()
    
    if not chat_id: return "Missing chat_id", 400
    
    # ✅ СОХРАНЯЕМ сообщение пользователя в базу данных сайта
    if user_message:
        db.save_message(chat_id, "user", user_message, None)

    # Вытаскиваем всю историю сообщений из БД (теперь при обновлении страницы всё подгрузится)
    history = db.get_chat_messages(chat_id)
    messages_payload = []
    
    for msg in history:
        messages_payload.append({"role": msg['role'], "content": msg['content']})

    def generate_reply():
        OLLAMA_URL = "http://localhost:11434/api/chat"
        
        payload = {
            "model": "easygpt",
            "messages": messages_payload,
            "stream": True
        }
        
        full_ai_response = ""
        try:
            response = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=60)
            
            if response.status_code == 404:
                yield f"data: {json.dumps({'chunk': '⚠️ Оллама ответила 404. Убедись, что модель easygpt точно создана на твоем ПК.'})}\n\n"
                return

            response.raise_for_status() 

            for line in response.iter_lines():
                if line:
                    decoded = line.decode('utf-8').strip()
                    try:
                        json_data = json.loads(decoded)
                        chunk = json_data.get('message', {}).get('content', '')
                        
                        if chunk:
                            full_ai_response += chunk
                            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                            
                        if json_data.get('done', False):
                            break
                    except: 
                        continue
                        
        except Exception as e:
            yield f"data: {json.dumps({'chunk': f'⚠️ Ошибка подключения: {str(e)}'})}\n\n"
        
        # ✅ ЖЕЛЕЗНО СОХРАНЯЕМ ответ ИИ в базу данных, чтобы он оставался после F5
        if full_ai_response.strip():
            db.save_message(chat_id, "assistant", full_ai_response)

    return Response(generate_reply(), mimetype='text/event-stream')

@app.route('/api/settings/password', methods=['POST'])
def api_change_password():
    if 'user_id' not in session: return jsonify({"error": "Не авторизован"}), 401
    
    old_password = request.form.get('old_password', '').strip()
    new_password = request.form.get('new_password', '').strip()
    
    if not old_password or not new_password:
        return jsonify({"error": "Заполните все поля!"}), 400
    if len(new_password) < 6:
        return jsonify({"error": "Новый пароль должен быть от 6 символов!"}), 400
        
    user = db.get_user_by_id(session['user_id'])
    
    if not user or not check_password_hash(user['password_hash'], old_password):
        return jsonify({"error": "❌ Неверный текущий пароль!"}), 403
        
    db.update_password(session['user_id'], new_password)
    return jsonify({"success": "✅ Пароль успешно изменен!"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)