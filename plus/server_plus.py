import socket
import threading
import struct
import json
import time
from datetime import datetime

class ChatProtocol:
    """Chat Protocol Definition"""
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
    
    # Error codes
    ERROR_BAD_REQUEST = 400
    ERROR_UNAUTHORIZED = 401
    ERROR_NICKNAME_EXISTS = 409
    ERROR_SERVER_ERROR = 500
    
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

class ChatServer:
    def __init__(self, host='localhost', port=12345):
        self.host = host
        self.port = port
        self.clients = {}  # {client_socket: user_info}
        self.nicknames = set()  # Set of active nicknames
        self.lock = threading.Lock()
        
    def broadcast(self, msg_type, data, exclude_client=None):
        """Broadcast message tới tất cả clients"""
        message = ChatProtocol.pack_message(msg_type, data)
        
        with self.lock:
            disconnected_clients = []
            for client_socket in self.clients:
                if client_socket != exclude_client:
                    try:
                        client_socket.send(message)
                    except:
                        disconnected_clients.append(client_socket)
            
            # Clean up disconnected clients
            for client in disconnected_clients:
                self.remove_client(client)
    
    def send_to_client(self, client_socket, msg_type, data):
        """Gửi message tới 1 client cụ thể"""
        try:
            message = ChatProtocol.pack_message(msg_type, data)
            client_socket.send(message)
            return True
        except:
            self.remove_client(client_socket)
            return False
    
    def remove_client(self, client_socket):
        """Xóa client khỏi server"""
        with self.lock:
            if client_socket in self.clients:
                user_info = self.clients[client_socket]
                nickname = user_info['nickname']
                
                # Remove from data structures
                del self.clients[client_socket]
                self.nicknames.discard(nickname)
                
                # Broadcast user leave
                leave_data = {
                    "nickname": nickname,
                    "message": f"{nickname} đã rời khỏi chat room",
                    "timestamp": time.time()
                }
                self.broadcast(ChatProtocol.USER_LEAVE, leave_data, client_socket)
                
                # Send updated user list
                self.broadcast_user_list()
                
                print(f"[SERVER] {nickname} đã ngắt kết nối")
                
        try:
            client_socket.close()
        except:
            pass
    
    def broadcast_user_list(self):
        """Broadcast danh sách users hiện tại"""
        with self.lock:
            user_list = [info['nickname'] for info in self.clients.values()]
        
        user_list_data = {
            "users": user_list,
            "count": len(user_list)
        }
        self.broadcast(ChatProtocol.USER_LIST, user_list_data)
    
    def handle_login_request(self, client_socket, nickname):
        """Xử lý yêu cầu đăng nhập"""
        with self.lock:
            if not nickname or len(nickname.strip()) == 0:
                error_data = {
                    "error_code": ChatProtocol.ERROR_BAD_REQUEST,
                    "error_message": "Nickname không được để trống",
                    "timestamp": time.time()
                }
                self.send_to_client(client_socket, ChatProtocol.ERROR, error_data)
                return False
            
            nickname = nickname.strip()
            
            if nickname in self.nicknames:
                error_data = {
                    "error_code": ChatProtocol.ERROR_NICKNAME_EXISTS,
                    "error_message": "Nickname đã tồn tại, vui lòng chọn tên khác",
                    "timestamp": time.time()
                }
                self.send_to_client(client_socket, ChatProtocol.ERROR, error_data)
                return False
            
            # Add client to server
            user_info = {
                "nickname": nickname,
                "joined_at": time.time(),
                "address": client_socket.getpeername()
            }
            self.clients[client_socket] = user_info
            self.nicknames.add(nickname)
        
        # Send login response
        login_response = {
            "success": True,
            "message": f"Chào mừng {nickname}!",
            "timestamp": time.time()
        }
        self.send_to_client(client_socket, ChatProtocol.LOGIN_RESPONSE, login_response)
        
        # Broadcast user join
        join_data = {
            "nickname": nickname,
            "message": f"{nickname} đã tham gia chat room",
            "timestamp": time.time()
        }
        self.broadcast(ChatProtocol.USER_JOIN, join_data, client_socket)
        
        # Send user list to all clients
        self.broadcast_user_list()
        
        print(f"[SERVER] {nickname} đã tham gia chat room")
        return True
    
    def handle_chat_message(self, client_socket, message_data):
        """Xử lý tin nhắn chat"""
        if client_socket not in self.clients:
            return
            
        user_info = self.clients[client_socket]
        nickname = user_info['nickname']
        
        chat_data = {
            "nickname": nickname,
            "message": message_data,
            "timestamp": time.time()
        }
        
        # Broadcast tới tất cả clients (kể cả người gửi để confirm)
        self.broadcast(ChatProtocol.CHAT_MESSAGE, chat_data)
        print(f"[CHAT] {nickname}: {message_data}")
    
    def handle_client_message(self, client_socket, msg_type, data):
        """Xử lý các loại message từ client"""
        try:
            if msg_type == ChatProtocol.LOGIN_REQUEST:
                return self.handle_login_request(client_socket, data)
            
            elif msg_type == ChatProtocol.CHAT_MESSAGE:
                self.handle_chat_message(client_socket, data)
                return True
            
            elif msg_type == ChatProtocol.PING:
                # Respond with PONG
                pong_data = {"timestamp": time.time()}
                self.send_to_client(client_socket, ChatProtocol.PONG, pong_data)
                return True
            
            else:
                error_data = {
                    "error_code": ChatProtocol.ERROR_BAD_REQUEST,
                    "error_message": f"Unknown message type: {msg_type}",
                    "timestamp": time.time()
                }
                self.send_to_client(client_socket, ChatProtocol.ERROR, error_data)
                return True
                
        except Exception as e:
            print(f"[SERVER] Error handling message: {e}")
            return False
    
    def handle_client(self, client_socket, address):
        """Xử lý kết nối từ client"""
        print(f"[SERVER] Xử lý kết nối từ {address}")
        buffer = b''
        
        try:
            while True:
                # Receive data
                data = client_socket.recv(4096)
                if not data:
                    break
                
                buffer += data
                
                # Process all complete messages in buffer
                while len(buffer) >= 9:
                    # Try to get message length
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
                                if not self.handle_client_message(client_socket, msg_type, msg_data):
                                    return  # Client should disconnect
                        else:
                            break  # Wait for more data
                    except Exception as e:
                        print(f"[SERVER] Error processing buffer: {e}")
                        buffer = b''  # Clear corrupted buffer
                        break
                        
        except Exception as e:
            print(f"[SERVER] Error in handle_client: {e}")
        finally:
            self.remove_client(client_socket)
    
    def start_server(self):
        """Khởi động server"""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            server.bind((self.host, self.port))
            server.listen(10)
            
            print(f"[SERVER] Chat server đang chạy tại {self.host}:{self.port}")
            print(f"[SERVER] Protocol version: {ChatProtocol.VERSION}")
            print("[SERVER] Đang chờ kết nối...")
            
            while True:
                try:
                    client_socket, address = server.accept()
                    
                    # Tạo thread để xử lý client
                    client_thread = threading.Thread(
                        target=self.handle_client, 
                        args=(client_socket, address)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    
                except Exception as e:
                    print(f"[SERVER] Error accepting connection: {e}")
                    
        except Exception as e:
            print(f"[SERVER] Error starting server: {e}")
        finally:
            server.close()

if __name__ == "__main__":
    # Tạo và khởi động server
    chat_server = ChatServer(
        host = '0.0.0.0'
    )
    try:
        chat_server.start_server()
    except KeyboardInterrupt:
        print("\n[SERVER] Server đang tắt...")
    except Exception as e:
        print(f"[SERVER] Lỗi: {e}")