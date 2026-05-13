import os
import timer_logic
from flask import Flask, request, render_template, jsonify, url_for
import threading
from time import localtime
from werkzeug.utils import secure_filename

app = Flask(__name__)

UPLOAD_FOLDER = os.path.join(app.static_folder, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_UPLOAD_EXT = {
    'png', 'jpg', 'jpeg', 'gif', 'webp',
    'mp4', 'webm', 'mov', 'm4v', 'mkv', 'avi'
}

@app.route('/')
def test():
    return render_template('test.html')

@app.route('/index')
def index():
    return render_template('index.html')

@app.route('/status')
def status():
    return jsonify(timer_logic.send_status())

@app.route('/reset_counter', methods=['POST'])
def reset_counter():
    timer_logic.reset_counter()
    return jsonify({'ok': True})

@app.route('/pause', methods=['POST'])
def pause():
    timer_logic.pause_flag = not timer_logic.pause_flag
    return jsonify({'paused': timer_logic.pause_flag})

@app.route('/skip_break', methods=['POST'])
def skip_break():
    # Помечаем текущий перерыв как завершённый
    timer_logic.skip_break_flag = True
    return jsonify({'ok': True})

@app.route('/update_settings', methods=['POST'])
def update_settings():
    data = request.get_json()
    if 'work' in data and data['work']:
        timer_logic.next_work_duration = int(data['work']) * 60
    if 'short' in data and data['short']:
        timer_logic.next_short_break = int(data['short']) * 60
    if 'long' in data and data['long']:
        timer_logic.next_long_break = int(data['long']) * 60
    return jsonify({'ok': True})

@app.route('/set_goal', methods=['POST'])
def set_goal():
    data = request.get_json()
    seconds = int(data.get('hours', 0)) * 3600 + int(data.get('minutes', 0)) * 60
    timer_logic.set_goal(seconds)
    return jsonify({'ok': True, 'goal': seconds})

@app.route('/manual_add', methods=['POST'])
def manual_add():
    """
    Ручное добавление отработанного времени.
    Ожидает JSON {"seconds": int, "add_to_total": bool}
    """
    data = request.get_json() or {}
    seconds = int(data.get('seconds', 0))
    add_to_total = bool(data.get('add_to_total', True))

    new_total = timer_logic.total_work_seconds_today
    if add_to_total and seconds > 0:
        new_total = timer_logic.add_manual_work(seconds)

    return jsonify({'ok': True, 'total_work': new_total})

@app.route('/upload_motivation', methods=['POST'])
def upload_motivation():
    """Загрузка файла мотивации (картинка или видео) в static/uploads."""
    file = request.files.get('file')
    if not file or file.filename == '':
        return jsonify({'ok': False, 'error': 'no_file'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_UPLOAD_EXT:
        return jsonify({'ok': False, 'error': 'bad_extension'}), 400

    filename = secure_filename(file.filename)
    name, dot_ext = os.path.splitext(filename)
    candidate = filename
    i = 1
    while os.path.exists(os.path.join(UPLOAD_FOLDER, candidate)):
        candidate = f"{name}_{i}{dot_ext}"
        i += 1

    save_path = os.path.join(UPLOAD_FOLDER, candidate)
    file.save(save_path)

    url = url_for('static', filename=f'uploads/{candidate}')
    return jsonify({'ok': True, 'url': url})


def _parse_able_to_work(value: str):
    """
    Парсим время окончания работы.
    Поддерживаем форматы:
    - '18:30'
    - '1830'
    - '18'  (то есть ровно в 18:00)
    Возвращаем (часы, минуты) или бросаем ValueError.
    """
    v = (value or '').strip()
    if not v:
        raise ValueError

    if ':' in v:
        parts = v.split(':')
        if len(parts) != 2:
            raise ValueError
        h = int(parts[0])
        m = int(parts[1])
    else:
        digits = ''.join(ch for ch in v if ch.isdigit())
        if not digits:
            raise ValueError
        if len(digits) in (3, 4):
            # 930 -> 9:30, 1830 -> 18:30
            h = int(digits[:-2])
            m = int(digits[-2:])
        elif len(digits) in (1, 2):
            # '9' или '18' -> 9:00 / 18:00
            h = int(digits)
            m = 0
        else:
            raise ValueError

    if h < 0 or h > 23 or m < 0 or m > 59:
        raise ValueError
    return h, m

@app.route('/start', methods=['POST'])
def start():
    able_to_work = request.form['able_to_work']
    no_break     = request.form.get('no_break',    '').strip() or '25'
    short_break  = request.form.get('short_break', '').strip() or '5'
    long_break   = request.form.get('long_break',  '').strip() or '15'

    try:
        h, m = _parse_able_to_work(able_to_work)
    except Exception:
        return render_template(
            'error.html',
            error_message="Неверный формат времени. Введите, например, 1830 или 18:30."
        )

    now = localtime()
    local_time = now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec

    if (h * 3600 + m * 60) - local_time <= 0:
        return render_template('error.html', error_message="Указанное время уже прошло. Укажите время в будущем.")

    # Нормализуем в формат HH:MM для логики таймера
    able_to_work_norm = f"{h:02d}:{m:02d}"

    timer_logic.stop_flag  = True
    timer_logic.pause_flag = False
    timer_logic.timer_finished = False

    threading.Thread(
        target=timer_logic.run_timer,
        args=(able_to_work_norm, no_break, short_break, long_break),
        daemon=True
    ).start()

    return render_template('started.html')

@app.route('/stop', methods=['POST'])
def stop():
    timer_logic.stop_flag  = True
    timer_logic.pause_flag = False
    timer_logic.now        = [None, 0, 0]
    timer_logic.timer_finished = False
    return render_template('test.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
