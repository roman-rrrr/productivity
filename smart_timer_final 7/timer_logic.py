import time
import os
import json
from time import localtime
from datetime import date, timedelta

stop_flag  = False
pause_flag = False
now        = [None, 0, 0]
timer_finished = False

# Тип текущего перерыва: None / 'short' / 'long'
current_break_type = None
# Флаг принудительного скипа текущего перерыва
skip_break_flag = False

# Параметры текущей сессии (для временной шкалы)
session_total_seconds   = 0
session_elapsed_seconds = 0
session_work_dur        = 0
session_short_dur       = 0
session_long_dur        = 0

# Изменяемые настройки прямо во время сессии (следующий цикл)
next_work_duration  = None  # секунды, None = не менять
next_short_break    = None
next_long_break     = None

# ─── DAILY COUNTER ───
COUNTER_FILE  = 'daily_counter.json'
PROGRESS_FILE = 'progress.json'

def _load_counter():
    today = str(date.today())
    try:
        with open(COUNTER_FILE) as f:
            data = json.load(f)
        if data.get('date') == today:
            return data.get('seconds', 0)
    except:
        pass
    return 0

def _save_counter(seconds):
    try:
        with open(COUNTER_FILE, 'w') as f:
            json.dump({'date': str(date.today()), 'seconds': seconds}, f)
    except:
        pass

total_work_seconds_today = _load_counter()

def reset_counter():
    global total_work_seconds_today
    total_work_seconds_today = 0
    _save_counter(0)

def add_manual_work(seconds: int):
    """
    Ручное добавление отработанного времени.
    Используется, когда пользователь хочет досчитать оффлайн‑активность.
    """
    global total_work_seconds_today
    seconds = int(max(0, seconds))
    if seconds == 0:
        return total_work_seconds_today
    total_work_seconds_today += seconds
    _save_counter(total_work_seconds_today)
    update_streak(total_work_seconds_today)
    return total_work_seconds_today

# ─── PROGRESS / STREAKS ───
def load_progress():
    try:
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    except:
        return {
            'goal_seconds': 0,
            'streak': 0,
            'last_work_date': '',
            'record_seconds': 0,
        }

def save_progress(data):
    try:
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(data, f)
    except:
        pass

def get_progress():
    return load_progress()

def update_streak(worked_seconds):
    """Вызывается в конце дня или при достижении цели."""
    data = load_progress()
    today = str(date.today())
    yesterday = str(date.today() - timedelta(days=1))

    if data.get('last_work_date') == yesterday:
        data['streak'] = data.get('streak', 0) + 1
    elif data.get('last_work_date') != today:
        data['streak'] = 1

    data['last_work_date'] = today
    if worked_seconds > data.get('record_seconds', 0):
        data['record_seconds'] = worked_seconds

    save_progress(data)
    return data

def set_goal(seconds):
    data = load_progress()
    data['goal_seconds'] = seconds
    save_progress(data)

# ─── FORMAT ───
def format_time(seconds):
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0: return f"{h} ч {m} мин {s} сек"
    if m == 0: return f"{s} сек"
    return f"{m} мин {s} сек"

# ─── STATUS ───
def send_status():
    global now, timer_finished, total_work_seconds_today, current_break_type
    global session_total_seconds, session_elapsed_seconds
    global session_work_dur, session_short_dur, session_long_dur
    prog = load_progress()
    base = {
        'total_work': total_work_seconds_today,
        'goal':       prog.get('goal_seconds', 0),
        'streak':     prog.get('streak', 0),
        'record':     prog.get('record_seconds', 0),
        'paused':     pause_flag,
        # информация о типе текущего перерыва для фронтенда
        'break_type': current_break_type,
        # параметры временной шкалы
        'session_total':   session_total_seconds,
        'session_elapsed': session_elapsed_seconds,
        'work_dur':        session_work_dur,
        'short_dur':       session_short_dur,
        'long_dur':        session_long_dur,
    }
    if timer_finished:
        return {**base, '1': ['Работа завершена', ''], '2': ['', ''], 'mode': 'finished'}
    if pause_flag:
        return {**base,
                '1': ['Пауза — не забудь вернуться', ''],
                '2': ['было: ', format_time(now[1])],
                'mode': 'paused'}
    if now[0] == 'work':
        return {**base,
                '1': ['Вы работаете уже: ', format_time(now[1])],
                '2': ['До перерыва: ',       format_time(now[2])],
                'mode': 'work'}
    if now[0] == 'chill':
        return {**base,
                '1': ['Перерыв: ',     format_time(now[1])],
                '2': ['До работы: ',   format_time(now[2])],
                'mode': 'chill'}
    return {**base, '1': ['Ожидание', ''], '2': ['', ''], 'mode': 'waiting'}

# ─── TIMER ───
def run_timer(_1, _2, _3, _4):
    global stop_flag, pause_flag, now, timer_finished, total_work_seconds_today
    global next_work_duration, next_short_break, next_long_break, current_break_type, skip_break_flag
    global session_total_seconds, session_elapsed_seconds
    global session_work_dur, session_short_dur, session_long_dur

    stop_flag  = False
    pause_flag = False
    timer_finished = False
    skip_break_flag = False

    ct = localtime()
    local_time = ct.tm_hour * 3600 + ct.tm_min * 60 + ct.tm_sec
    h, m = [int(i) for i in _1.split(":")]
    work_time = h * 3600 + m * 60 - local_time

    work_dur   = int(_2) * 60
    short_dur  = int(_3) * 60
    long_dur   = int(_4) * 60

    # Инициализируем параметры сессии
    session_total_seconds   = work_time
    session_elapsed_seconds = 0
    session_work_dur        = work_dur
    session_short_dur       = short_dur
    session_long_dur        = long_dur

    elapsed_time = 0
    cycle_count  = 0

    current_break_type = None

    while elapsed_time < work_time and not stop_flag:
        # Применяем изменения настроек перед циклом
        if next_work_duration is not None:
            work_dur = next_work_duration; next_work_duration = None
        if next_short_break is not None:
            short_dur = next_short_break; next_short_break = None
        if next_long_break is not None:
            long_dur = next_long_break; next_long_break = None

        is_long_break  = (cycle_count > 0 and cycle_count % 4 == 0)
        break_duration = long_dur if is_long_break else short_dur

        # Перед началом блока работы считаем, что перерыва нет
        current_break_type = None

        # РАБОТА
        second = 0
        while second < work_dur:
            if stop_flag: return
            # ПАУЗА
            while pause_flag and not stop_flag:
                now = ['work', second, work_dur - second]
                time.sleep(0.2)
            if stop_flag: return
            if elapsed_time >= work_time:
                _finish(); return
            now = ['work', second, work_dur - second]
            total_work_seconds_today += 1
            _save_counter(total_work_seconds_today)
            update_streak(total_work_seconds_today)
            time.sleep(1)
            elapsed_time += 1
            session_elapsed_seconds = elapsed_time
            second += 1

        cycle_count += 1
        if elapsed_time >= work_time: _finish(); return

        _play('Длинныи_.mp3' if is_long_break else 'Короткии_.mp3')

        # Помечаем тип следующего перерыва
        current_break_type = 'long' if is_long_break else 'short'

        # ПЕРЕРЫВ
        second = 0
        while second < break_duration:
            if stop_flag:
                return
            # Скип перерыва по запросу с фронтенда
            if skip_break_flag:
                skip_break_flag = False
                break
            while pause_flag and not stop_flag:
                now = ['chill', second, break_duration - second]
                time.sleep(0.2)
            if stop_flag:
                return
            if elapsed_time >= work_time:
                _finish()
                return
            now = ['chill', second, break_duration - second]
            time.sleep(1)
            elapsed_time += 1
            session_elapsed_seconds = elapsed_time
            second += 1

        if elapsed_time < work_time:
            _play('Пора_возвращаться_к_работе.mp3')

    _finish()

def _finish():
    global now, timer_finished
    timer_finished = True
    now = [None, 0, 0]
    _play('Время_истекло.mp3')

def _play(filename):
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_dir, 'sounds', filename)
        os.system(f"afplay '{path}' &")
    except:
        pass
