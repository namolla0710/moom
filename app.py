from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, rooms

app = Flask(__name__)
app.config['SECRET_KEY'] = 'a-super-secret-key-for-this-webrtc-project-final'
socketio = SocketIO(app, cors_allowed_origins="*")

# 활성화된 방의 정보를 저장할 딕셔너리
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
    """메인 페이지를 렌더링합니다."""
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    """새로운 클라이언트가 연결되면, 현재 활성화된 방 목록을 보내줍니다."""
    print(f"✅ 클라이언트 연결됨: {request.sid}")
    emit('update_room_list', get_rooms_info())

@socketio.on('disconnect')
def handle_disconnect():
    """클라이언트 연결이 끊겼을 때의 처리"""
    user_sid = request.sid
    room_to_leave = None
    print(f"❌ 클라이언트 연결 끊김: {user_sid}")
    
    # 해당 유저가 어떤 방에 있었는지 찾아서 처리
    for room_name, data in list(active_rooms.items()):
        if user_sid in data['users']:
            # 해당 방의 유저 목록에서 제거
            del data['users'][user_sid]
            room_to_leave = room_name
            print(f"🚪 {user_sid}님이 '{room_name}' 방에서 나갔습니다.")
            
            # 방에 아무도 남지 않았다면 방을 완전히 삭제
            if not data['users']:
                print(f"💥 방 '{room_name}'이 비어서 삭제됩니다.")
                del active_rooms[room_name]
            break
    
    if room_to_leave:
        # 해당 방에 있던 다른 유저들에게 퇴장 사실 알림
        emit('user-left', {'sid': user_sid}, to=room_to_leave)
        # 모든 클라이언트에게 변경된 방 목록 정보 전송
        socketio.emit('update_room_list', get_rooms_info())

@socketio.on('join')
def handle_join(data):
    """사용자가 특정 방에 참여를 요청했을 때의 처리"""
    nickname = data.get('nickname', '익명')
    room_name = data.get('room_name')
    password = data.get('password')

    if not room_name:
        return

    # 방이 이미 존재하고 비밀번호가 틀렸을 경우, 입장 실패 처리
    if room_name in active_rooms:
        if active_rooms[room_name]['password'] and active_rooms[room_name]['password'] != password:
            emit('join_failed', {'message': '비밀번호가 틀렸습니다.'})
            return
    # 방이 존재하지 않으면 새로 생성
    else:
        active_rooms[room_name] = {'password': password, 'users': {}}

    join_room(room_name)
    active_rooms[room_name][request.sid] = nickname

    # 2인 즉시 연결을 위해, 새로 들어온 유저에게만 기존 유저 목록을 전달
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

@socketio.on('chat')
def handle_chat(data):
    """채팅 메시지를 해당 방의 모든 유저에게 중계"""
    room = data.get('room')
    if room in active_rooms and request.sid in active_rooms[room]['users']:
        sender_nickname = active_rooms[room][request.sid]
        emit('chat', {
            'from_sid': request.sid,
            'nickname': sender_nickname,
            'message': data.get('message')
        }, to=room)

@socketio.on('offer')
def handle_offer(data):
    emit('offer', data, to=data.get('target_sid'))

@socketio.on('answer')
def handle_answer(data):
    emit('answer', data, to=data.get('target_sid'))

@socketio.on('ice-candidate')
def handle_ice_candidate(data):
    emit('ice-candidate', data, to=data.get('target_sid'))

if __name__ == '__main__':
    print("🚀 Flask-SocketIO 서버가 http://localhost:8080 에서 실행됩니다.")
    socketio.run(app, host='0.0.0.0', port=8080, debug=True)