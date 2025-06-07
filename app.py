from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, rooms

app = Flask(__name__)
app.config['SECRET_KEY'] = 'this-is-the-final-super-secret-key-i-promise'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- 상태 관리 변수 ---
# 구조: {'room_name': {'password': '123', 'users': {'sid1': 'Alice', 'sid2': 'Bob'}}}
active_rooms = {}
# 전체 접속자 수 관리를 위한 변수
total_users_count = 0

def get_rooms_info():
    """클라이언트에 전송할 현재 방 목록 정보를 생성합니다."""
    return [
        {'name': room, 'user_count': len(data['users']), 'has_password': bool(data['password'])}
        for room, data in active_rooms.items()
    ]

def broadcast_stats():
    """모든 클라이언트에게 통계 정보(방 목록, 총 접속자)를 브로드캐스트합니다."""
    socketio.emit('update_stats', {
        'rooms': get_rooms_info(),
        'total_users': total_users_count
    })

@app.route('/')
def index():
    """메인 페이지를 렌더링합니다."""
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    """클라이언트 연결 시 총 접속자 수를 늘리고, 통계 정보를 전송합니다."""
    global total_users_count
    total_users_count += 1
    print(f"✅ 클라이언트 연결됨: {request.sid} (현재 총 접속자: {total_users_count})")
    broadcast_stats()

@socketio.on('disconnect')
def handle_disconnect():
    """클라이언트 연결 해제 시 관련 정보를 정리하고 브로드캐스트합니다."""
    global total_users_count
    total_users_count = max(0, total_users_count - 1)
    user_sid = request.sid
    
    print(f"❌ 클라이언트 연결 끊김: {request.sid} (현재 총 접속자: {total_users_count})")
    
    # 해당 유저가 어떤 방에 있었는지 찾아서 처리
    for room_name, data in list(active_rooms.items()):
        if user_sid in data['users']:
            nickname = data['users'].pop(user_sid) # 유저를 삭제하고 닉네임을 가져옴
            print(f"🚪 {nickname}({user_sid})님이 '{room_name}' 방에서 나갔습니다.")

            # 해당 방에 있던 다른 유저들에게 퇴장 사실 알림
            emit('user-left', {'sid': user_sid}, to=room_name)
            
            # 퇴장 시스템 메시지 전송
            emit('system_message', {'message': f"'{nickname}'님이 퇴장했습니다."}, to=room_name)
            
            # 방 인원수 업데이트 정보 전송
            emit('room_status_update', {'user_count': len(data['users'])}, to=room_name)

            # 방에 아무도 남지 않았다면 방을 완전히 삭제
            if not data['users']:
                print(f"💥 방 '{room_name}'이 비어서 삭제됩니다.")
                del active_rooms[room_name]
            
            break # 유저는 하나의 방에만 있을 수 있으므로 반복 중단
    
    # 방 목록이 변경되었을 수 있으므로 전체 통계 다시 전송
    broadcast_stats()

@socketio.on('join')
def handle_join(data):
    """사용자가 특정 방에 참여를 요청했을 때의 처리"""
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

    # 2인 즉시 연결을 위해, 새로 들어온 유저에게만 기존 유저 목록을 전달
    existing_users = [{'sid': sid, 'nickname': nick} for sid, nick in active_rooms[room_name]['users'].items() if sid != request.sid]
    
    emit('join_success', {
        'room': room_name,
        'nickname': nickname,
        'existing_users': existing_users,
        'room_password': active_rooms[room_name]['password']
    })
    
    # 다른 사람들에게는 'user-joined-info' 이벤트를 보내 닉네임 목록만 갱신하게 함
    emit('user-joined-info', {'sid': request.sid, 'nickname': nickname}, to=room_name, skip_sid=request.sid)

    # 입장 시스템 메시지 및 인원수 업데이트
    emit('system_message', {'message': f"'{nickname}'님이 입장했습니다."}, to=room_name)
    emit('room_status_update', {'user_count': len(active_rooms[room_name]['users'])}, to=room_name)

    print(f"👍 {nickname}({request.sid})님이 '{room_name}' 방에 성공적으로 참여했습니다.")
    broadcast_stats()


@socketio.on('change_nickname')
def handle_nickname_change(data):
    """닉네임 변경 요청 처리"""
    room = data.get('room')
    new_nickname = data.get('new_nickname')
    if room in active_rooms and request.sid in active_rooms[room]['users']:
        old_nickname = active_rooms[room][request.sid]
        active_rooms[room][request.sid] = new_nickname
        print(f"✏️ {request.sid} 님이 닉네임을 '{old_nickname}' -> '{new_nickname}'(으)로 변경했습니다.")
        
        # 닉네임 변경 사실 알림
        emit('nickname_changed', {'sid': request.sid, 'new_nickname': new_nickname}, to=room)
        # 닉네임 변경 시스템 메시지 추가
        emit('system_message', {'message': f"'{old_nickname}'님이 닉네임을 '{new_nickname}'(으)로 변경했습니다."}, to=room)

@socketio.on('media_status_change')
def handle_media_status_change(data):
    """음소거/카메라 끄기 상태 변경 처리"""
    emit('user_media_status_changed', {
        'sid': request.sid,
        'mediaType': data.get('mediaType'),
        'status': data.get('status')
    }, to=data.get('room'), skip_sid=request.sid)

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