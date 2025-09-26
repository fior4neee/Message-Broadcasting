import socket
import threading
import struct
import json
import time
from datetime import datetime

class ChatProtocol:
    """Chat Protocol Definition - Phải giống với server"""
    MAGIC = 0xCAFE
    VERSION = 0x01
    
    # Message types
    LOGIN_REQUEST = 0x01
    LOGIN_RESPONSE = 0x02
    CHAT_MESSAGE = 0x03
    USER_JOIN = 0x04
    USER_LEAVE = 0x05
    USER_LIST = 0x06
    PING = 0x07
    PONG = 0x08
    ERROR = 0x09
    
    @staticmethod
    def pack_message(msg_type, data):
        """Đóng gói message theo protocol"""
        if isinstance(data, dict):
            data_bytes = json.dumps(data, ensure_ascii=False).encode('utf-8')
        elif isinstance(data, str):
            data_bytes = data.encode('utf-8')
        else:
            data_bytes = str(data).encode('utf-8')
        
        # Header: Magic(2) + Version(1) + Reserved(1) + Type(1) + Length(4) = 9 bytes
        header = struct.pack('!HBBBL', 
                           ChatProtocol.MAGIC,
                           ChatProtocol.VERSION, 
                           0,  # Reserved
                           msg_type,
                           len(data_bytes))
        
        return header + data_bytes
    
    @staticmethod
    def unpack_message(data):
        """Giải nén message"""
        if len(data) < 9:
            return None, None
            
        try:
            magic, version, reserved, msg_type, length = struct.unpack('!HBBBL', data[:9])
            
            if magic != ChatProtocol.MAGIC:
                raise ValueError("Invalid magic number")
                
            if version != ChatProtocol.VERSION:
                raise ValueError("Unsupported version")
                
            if len(data) < 9 + length:
                return None, None  # Chưa nhận đủ data
                
            message_data = data[9:9+length].decode('utf-8')
            
            # Try parse JSON
            try:
                message_data = json.loads(message_data)
            except:
                pass  # Keep as string if not JSON
                
            return msg_type, message_data
        except Exception as e:
            raise ValueError(f"Failed to unpack message: {e}")

class ChatClient:
    def __init__(self, host='localhost', port=12345):
        self.host = host
        self.port = port
        self.nickname = ""
        self.client_socket = None
        self.running = False
        self.logged_in = False
        self.user_list = []
        
    def format_timestamp(self, timestamp):
        """Format timestamp thành string đẹp"""
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%H:%M:%S")
    
    def send_message(self, msg_type, data):
        """Gửi message tới server"""
        try:
            message = ChatProtocol.pack_message(msg_type, data)
            self.client_socket.send(message)
            return True
        except Exception as e:
            print(f"[CLIENT] Lỗi gửi message: {e}")
            return False
    
    def handle_login_response(self, data):
        """Xử lý phản hồi đăng nhập"""
        if isinstance(data, dict):
            if data.get('success'):
                self.logged_in = True
                timestamp = self.format_timestamp(data.get('timestamp', time.time()))
                print(f"[{timestamp}] {data.get('message', 'Đăng nhập thành công!')}")
                print("-" * 50)
            else:
                print(f"[ERROR] Đăng nhập thất bại: {data.get('message', 'Unknown error')}")
        else:
            print(f"[INFO] {data}")
    
    def handle_chat_message(self, data):
        """Xử lý tin nhắn chat"""
        if isinstance(data, dict):
            nickname = data.get('nickname', 'Unknown')
            message = data.get('message', '')
            timestamp = self.format_timestamp(data.get('timestamp', time.time()))
            
            # Không in lại tin nhắn của chính mình (đã in khi gửi)
            if nickname != self.nickname:
                print(f"[{timestamp}] {nickname}: {message}")
        else:
            print(f"[CHAT] {data}")
    
    def handle_user_join(self, data):
        """Xử lý thông báo user tham gia"""
        if isinstance(data, dict):
            nickname = data.get('nickname', 'Unknown')
            timestamp = self.format_timestamp(data.get('timestamp', time.time()))
            print(f"[{timestamp}] >>> {nickname} đã tham gia chat room <<<")
        else:
            print(f"[JOIN] {data}")
    
    def handle_user_leave(self, data):
        """Xử lý thông báo user rời đi"""
        if isinstance(data, dict):
            nickname = data.get('nickname', 'Unknown')
            timestamp = self.format_timestamp(data.get('timestamp', time.time()))
            print(f"[{timestamp}] <<< {nickname} đã rời khỏi chat room >>>")
        else:
            print(f"[LEAVE] {data}")
    
    def handle_user_list(self, data):
        """Xử lý danh sách users"""
        if isinstance(data, dict):
            users = data.get('users', [])
            count = data.get('count', len(users))
            self.user_list = users
            
            print(f"[INFO] Có {count} người trong chat room: {', '.join(users)}")
    
    def handle_error(self, data):
        """Xử lý thông báo lỗi"""
        if isinstance(data, dict):
            error_code = data.get('error_code', 0)
            error_message = data.get('error_message', 'Unknown error')
            timestamp = self.format_timestamp(data.get('timestamp', time.time()))
            
            print(f"[{timestamp}] ERROR {error_code}: {error_message}")
            
            # Nếu lỗi nickname exists, yêu cầu nhập lại
            if error_code == 409:  # NICKNAME_EXISTS
                return False  # Signal to retry login
        else:
            print(f"[ERROR] {data}")
        return True
    
    def handle_pong(self, data):
        """Xử lý PONG response"""
        # Có thể dùng để đo ping time
        pass
    
    def receive_messages(self):
        """Nhận và xử lý messages từ server"""
        buffer = b''
        
        while self.running:
            try:
                data = self.client_socket.recv(4096)
                if not data:
                    print("[CLIENT] Mất kết nối với server")
                    break
                
                buffer += data
                
                # Process all complete messages in buffer
                while len(buffer) >= 9:
                    try:
                        length = struct.unpack('!L', buffer[5:9])[0]
                        total_msg_len = 9 + length
                        
                        if len(buffer) >= total_msg_len:
                            # Extract complete message
                            msg_bytes = buffer[:total_msg_len]
                            buffer = buffer[total_msg_len:]
                            
                            # Process message
                            msg_type, msg_data = ChatProtocol.unpack_message(msg_bytes)
                            if msg_type is not None:
                                self.handle_received_message(msg_type, msg_data)
                        else:
                            break  # Wait for more data
                    except Exception as e:
                        print(f"[CLIENT] Error processing buffer: {e}")
                        buffer = b''
                        break
                        
            except Exception as e:
                if self.running:
                    print(f"[CLIENT] Lỗi nhận message: {e}")
                break
                
        self.running = False
    
    def handle_received_message(self, msg_type, data):
        """Xử lý message nhận được từ server"""
        if msg_type == ChatProtocol.LOGIN_RESPONSE:
            self.handle_login_response(data)
        
        elif msg_type == ChatProtocol.CHAT_MESSAGE:
            self.handle_chat_message(data)
        
        elif msg_type == ChatProtocol.USER_JOIN:
            self.handle_user_join(data)
        
        elif msg_type == ChatProtocol.USER_LEAVE:
            self.handle_user_leave(data)
        
        elif msg_type == ChatProtocol.USER_LIST:
            self.handle_user_list(data)
        
        elif msg_type == ChatProtocol.ERROR:
            return self.handle_error(data)
        
        elif msg_type == ChatProtocol.PONG:
            self.handle_pong(data)
        
        else:
            print(f"[CLIENT] Unknown message type: {msg_type}")
        
        return True
    
    def send_chat_message(self, message):
        """Gửi tin nhắn chat"""
        if self.logged_in and message.strip():
            if self.send_message(ChatProtocol.CHAT_MESSAGE, message):
                # In tin nhắn của chính mình
                timestamp = self.format_timestamp(time.time())
                print(f"[{timestamp}] {self.nickname}: {message}")
                return True
        return False
    
    def login(self):
        """Đăng nhập với nickname"""
        max_retries = 3
        for attempt in range(max_retries):
            if attempt > 0:
                print(f"\nThử lại lần {attempt + 1}/{max_retries}")
            
            # Send login request
            if self.send_message(ChatProtocol.LOGIN_REQUEST, self.nickname):
                # Wait for response (timeout after 5 seconds)
                start_time = time.time()
                while time.time() - start_time < 5:
                    if self.logged_in:
                        return True
                    time.sleep(0.1)
                
                if not self.logged_in:
                    print("[ERROR] Timeout waiting for login response")
            else:
                print("[ERROR] Không thể gửi login request")
        
        return False
    
    def send_ping(self):
        """Gửi PING để test connection"""
        ping_data = {"timestamp": time.time()}
        return self.send_message(ChatProtocol.PING, ping_data)
    
    def process_command(self, message):
        """Xử lý các lệnh đặc biệt"""
        if not message.startswith('/'):
            return False
        
        cmd = message.lower().split()[0]
        
        if cmd in ['/quit', '/exit', '/q']:
            return 'quit'
        
        elif cmd == '/ping':
            if self.send_ping():
                print("[INFO] Ping sent")
            return 'continue'
        
        elif cmd == '/users' or cmd == '/list':
            if self.user_list:
                print(f"[INFO] Users online ({len(self.user_list)}): {', '.join(self.user_list)}")
            else:
                print("[INFO] Không có thông tin danh sách users")
            return 'continue'
        
        elif cmd == '/help':
            print("\n=== COMMANDS ===")
            print("/quit, /exit, /q - Thoát khỏi chat")
            print("/ping - Test connection")
            print("/users, /list - Xem danh sách users")
            print("/help - Hiển thị help")
            print("===============\n")
            return 'continue'
        
        else:
            print(f"[INFO] Lệnh không hợp lệ: {cmd}. Gõ /help để xem danh sách lệnh")
            return 'continue'
    
    def input_loop(self):
        """Vòng lặp nhập input từ user"""
        while self.running:
            try:
                if self.logged_in:
                    message = input().strip()
                    
                    if message:
                        # Check for commands
                        cmd_result = self.process_command(message)
                        if cmd_result == 'quit':
                            break
                        elif cmd_result == 'continue':
                            continue
                        
                        # Send regular message
                        if not self.send_chat_message(message):
                            print("[ERROR] Không thể gửi tin nhắn")
                else:
                    time.sleep(0.1)  # Wait for login
                    
            except EOFError:
                break
            except KeyboardInterrupt:
                break
        
        self.disconnect()
    
    def connect_and_run(self):
        """Kết nối tới server và chạy client"""
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.host, self.port))
            self.running = True
            
            print(f"[CLIENT] Đã kết nối tới server {self.host}:{self.port}")
            
            # Start receive thread
            receive_thread = threading.Thread(target=self.receive_messages)
            receive_thread.daemon = True
            receive_thread.start()
            
            # Login
            if self.login():
                print("Bạn có thể bắt đầu chat! Gõ /help để xem lệnh hỗ trợ")
                
                # Start input loop
                self.input_loop()
            else:
                print("[ERROR] Không thể đăng nhập")
                
        except Exception as e:
            print(f"[CLIENT] Lỗi kết nối: {e}")
        finally:
            self.disconnect()
    
    def disconnect(self):
        """Ngắt kết nối"""
        print("\n[CLIENT] Đang ngắt kết nối...")
        self.running = False
        self.logged_in = False
        
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass

def main():
    print("=== CHAT CLIENT (Improved Protocol) ===")
    print("Protocol version:", ChatProtocol.VERSION)
    
    # Nhập nickname
    while True:
        nickname = input("Nhập nickname của bạn: ").strip()
        if nickname and len(nickname) <= 50:
            break
        print("Nickname không được để trống và không quá 50 ký tự!")
    
    # Server settings
    server_input = input("Nhập địa chỉ server (Enter cho localhost:12345): ").strip()
    
    if server_input:
        try:
            if ':' in server_input:
                host, port = server_input.split(':', 1)
                port = int(port)
            else:
                host = server_input
                port = 12345
        except:
            print("Địa chỉ server không hợp lệ!")
            return
    else:
        host = 'localhost'
        port = 12345
    
    # Create and run client
    client = ChatClient(host, port)
    client.nickname = nickname
    
    print(f"\nĐang kết nối tới {host}:{port}...")
    print("-" * 50)
    
    try:
        client.connect_and_run()
    except KeyboardInterrupt:
        print("\n[CLIENT] Ngắt kết nối bởi người dùng")
        client.disconnect()

if __name__ == "__main__":
    main()