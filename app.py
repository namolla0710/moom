from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, rooms

app = Flask(__name__)
app.config['SECRET_KEY'] = 'a-super-secret-key-for-this-webrtc-project-final'
socketio = SocketIO(app, cors_allowed_origins="*")

# 구조: {'room_name': {'password': '123', 'users': {'sid1': 'Alice', 'sid2': 'Bob'}}}
active_rooms = {}

def get_rooms_info():
    """클라이언트에 전송할 현재 방 목록 정보를 생성합니다."""
    rooms_info = []
    for room, data in active_rooms.items():
        rooms_info.append({
            'name': room,
            'user_count': len(data['users']),
            'has_password': bool(data['password'])
        })
    return rooms_info

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    print(f"✅ 클라이언트 연결됨: {request.sid}")
    emit('update_room_list', get_rooms_info())

@socketio.on('disconnect')
def handle_disconnect():
    user_sid = request.sid
    room_to_leave = None
    print(f"❌ 클라이언트 연결 끊김: {user_sid}")
    
    for room_name, data in list(active_rooms.items()):
        if user_sid in data['users']:
            del data['users'][user_sid]
            room_to_leave = room_name
            print(f"🚪 {user_sid}님이 '{room_name}' 방에서 나갔습니다.")
            
            if not data['users']:
                print(f"💥 방 '{room_name}'이 비어서 삭제됩니다.")
                del active_rooms[room_name]
            break
    
    if room_to_leave:
        emit('user-left', {'sid': user_sid}, to=room_to_leave)
        socketio.emit('update_room_list', get_rooms_info())

@socketio.on('join')
def handle_join(data):
    nickname = data.get('nickname', '익명')
    room_name = data.get('room_name')
    password = data.get('password')

    if not room_name: return

    if room_name in active_rooms:
        if active_rooms[room_name]['password'] and active_rooms[room_name]['password'] != password:
            emit('join_failed', {'message': '비밀번호가 틀렸습니다.'})
            return
    else:
        active_rooms[room_name] = {'password': password, 'users': {}}

    join_room(room_name)
    active_rooms[room_name][request.sid] = nickname

    # ✨ 2인 즉시 연결을 위해, 새로 들어온 유저에게만 기존 유저 목록을 전달
    # 기존 유저들에게는 'user-joined'를 보내지 않음으로써, 연결 주도권을 새로 들어온 유저에게만 부여
    existing_users = [
        {'sid': sid, 'nickname': nick}
        for sid, nick in active_rooms[room_name]['users'].items()
        if sid != request.sid
    ]
    emit('join_success', {
        'room': room_name,
        'nickname': nickname,
        'existing_users': existing_users
    })

    # 다른 사람들에게는 'user-joined-info' 이벤트를 보내 닉네임 목록만 갱신하게 함
    emit('user-joined-info', {
        'sid': request.sid,
        'nickname': nickname
    }, to=room_name, skip_sid=request.sid)

    print(f"👍 {nickname}({request.sid})님이 '{room_name}' 방에 성공적으로 참여했습니다.")
    socketio.emit('update_room_list', get_rooms_info())

# --- ✨ 새로운 이벤트 핸들러 추가 ---

@socketio.on('change_nickname')
def handle_nickname_change(data):
    """닉네임 변경 요청 처리"""
    room = data.get('room')
    new_nickname = data.get('new_nickname')
    if room in active_rooms and request.sid in active_rooms[room]['users']:
        active_rooms[room][request.sid] = new_nickname
        print(f"✏️ {request.sid} 님이 닉네임을 '{new_nickname}'으로 변경했습니다.")
        # 해당 방의 모든 유저에게 닉네임 변경 사실 알림
        emit('nickname_changed', {
            'sid': request.sid,
            'new_nickname': new_nickname
        }, to=room)

@socketio.on('media_status_change')
def handle_media_status_change(data):
    """음소거/카메라 끄기 상태 변경 처리"""
    room = data.get('room')
    if room in active_rooms:
        # 요청한 유저를 제외한 모든 유저에게 상태 변경 사실 전달
        emit('user_media_status_changed', {
            'sid': request.sid,
            'mediaType': data.get('mediaType'),
            'status': data.get('status')
        }, to=room, skip_sid=request.sid)

# --- 기존 시그널링 핸들러 (수정 없음) ---
@socketio.on('chat')
def handle_chat(data):
    room = data.get('room')
    if room in active_rooms and request.sid in active_rooms[room]['users']:
        sender_nickname = active_rooms[room][request.sid]
        emit('chat', { 'from_sid': request.sid, 'nickname': sender_nickname, 'message': data.get('message') }, to=room)

@socketio.on('offer')
def handle_offer(data): emit('offer', data, to=data.get('target_sid'))
@socketio.on('answer')
def handle_answer(data): emit('answer', data, to=data.get('target_sid'))
@socketio.on('ice-candidate')
def handle_ice_candidate(data): emit('ice-candidate', data, to=data.get('target_sid'))

if __name__ == '__main__':
    print("🚀 Flask-SocketIO 서버가 http://localhost:8080 에서 실행됩니다.")
    socketio.run(app, host='0.0.0.0', port=8080, debug=True)