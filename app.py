from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, rooms

app = Flask(__name__)
app.config['SECRET_KEY'] = 'this-is-the-truly-final-super-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# 구조: {'room_name': {'password': '123', 'users': {'sid1': 'Alice', 'sid2': 'Bob'}}}
active_rooms = {}
total_users_count = 0

def get_rooms_info():
    return [
        {'name': room, 'user_count': len(data['users']), 'has_password': bool(data['password'])}
        for room, data in active_rooms.items()
    ]

def broadcast_stats():
    socketio.emit('update_stats', {
        'rooms': get_rooms_info(),
        'total_users': total_users_count
    })

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    global total_users_count
    total_users_count += 1
    print(f"✅ 클라이언트 연결됨: {request.sid} (현재 총 접속자: {total_users_count})")
    broadcast_stats()

@socketio.on('disconnect')
def handle_disconnect():
    global total_users_count
    total_users_count = max(0, total_users_count - 1)
    user_sid = request.sid
    print(f"❌ 클라이언트 연결 끊김: {request.sid} (현재 총 접속자: {total_users_count})")
    
    for room_name, data in list(active_rooms.items()):
        if user_sid in data.get('users', {}):
            nickname = data['users'].pop(user_sid)
            print(f"🚪 {nickname}({user_sid})님이 '{room_name}' 방에서 나갔습니다.")
            
            emit('user-left', {'sid': user_sid}, to=room_name)
            emit('system_message', {'message': f"'{nickname}'님이 퇴장했습니다."}, to=room_name)
            emit('room_status_update', {'user_count': len(data['users'])}, to=room_name)

            if not data['users']:
                print(f"💥 방 '{room_name}'이 비어서 삭제됩니다.")
                del active_rooms[room_name]
            
            break
    broadcast_stats()

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
    # ✨ 버그 수정: 'users' 딕셔너리에 정확히 접근
    active_rooms[room_name]['users'][request.sid] = nickname

    existing_users = [{'sid': sid, 'nickname': nick} for sid, nick in active_rooms[room_name]['users'].items() if sid != request.sid]
    
    emit('join_success', {
        'room': room_name,
        'nickname': nickname,
        'existing_users': existing_users,
        'room_password': active_rooms[room_name]['password']
    })
    
    emit('user-joined-info', {'sid': request.sid, 'nickname': nickname}, to=room_name, skip_sid=request.sid)
    emit('system_message', {'message': f"'{nickname}'님이 입장했습니다."}, to=room_name)
    emit('room_status_update', {'user_count': len(active_rooms[room_name]['users'])}, to=room_name)

    print(f"👍 {nickname}({request.sid})님이 '{room_name}' 방에 성공적으로 참여했습니다.")
    broadcast_stats()

@socketio.on('change_nickname')
def handle_nickname_change(data):
    room = data.get('room')
    new_nickname = data.get('new_nickname')
    # ✨ 버그 수정: 'users' 딕셔너리에 정확히 접근
    if room in active_rooms and request.sid in active_rooms[room]['users']:
        old_nickname = active_rooms[room]['users'][request.sid]
        active_rooms[room]['users'][request.sid] = new_nickname
        print(f"✏️ {request.sid} 님이 닉네임을 '{old_nickname}' -> '{new_nickname}'(으)로 변경했습니다.")
        
        emit('nickname_changed', {'sid': request.sid, 'new_nickname': new_nickname}, to=room)
        emit('system_message', {'message': f"'{old_nickname}'님이 닉네임을 '{new_nickname}'(으)로 변경했습니다."}, to=room)

@socketio.on('media_status_change')
def handle_media_status_change(data):
    emit('user_media_status_changed', {'sid': request.sid, 'mediaType': data.get('mediaType'), 'status': data.get('status')}, to=data.get('room'), skip_sid=request.sid)

@socketio.on('chat')
def handle_chat(data):
    room = data.get('room')
    # ✨ 버그 수정: 'users' 딕셔너리에 정확히 접근
    if room in active_rooms and request.sid in active_rooms[room]['users']:
        sender_nickname = active_rooms[room]['users'][request.sid]
        emit('chat', {'from_sid': request.sid, 'nickname': sender_nickname, 'message': data.get('message')}, to=room)

# WebRTC 시그널링 핸들러 (수정 없음)
@socketio.on('offer')
def handle_offer(data): emit('offer', data, to=data.get('target_sid'))
@socketio.on('answer')
def handle_answer(data): emit('answer', data, to=data.get('target_sid'))
@socketio.on('ice-candidate')
def handle_ice_candidate(data): emit('ice-candidate', data, to=data.get('target_sid'))

if __name__ == '__main__':
    print("🚀 Flask-SocketIO 서버가 http://localhost:8080 에서 실행됩니다.")
    socketio.run(app, host='0.0.0.0', port=8080, debug=True)