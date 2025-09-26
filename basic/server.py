import socket
import threading
import time

class ChatServer:
    def __init__(self, host='localhost', port=12345):
        self.host = host
        self.port = port
        self.clients = []  # Danh sách các client đang kết nối
        self.nicknames = []  # Danh sách tên của các client
        
    def broadcast(self, message, sender_client=None):
        """Gửi tin nhắn tới tất cả client (trừ người gửi)"""
        for client in self.clients:
            if client != sender_client:  # Không gửi lại cho người gửi
                try:
                    client.send(message)
                except:
                    # Nếu không gửi được, xóa client khỏi danh sách
                    self.remove_client(client)
    
    def remove_client(self, client):
        """Xóa client khỏi server"""
        if client in self.clients:
            index = self.clients.index(client)
            self.clients.remove(client)
            nickname = self.nicknames[index]
            self.nicknames.remove(nickname)
            
            # Thông báo cho các client khác
            leave_message = f"{nickname} đã rời khỏi chat room!".encode('utf-8')
            self.broadcast(leave_message)
            print(f"[SERVER] {nickname} đã ngắt kết nối")
            client.close()
    
    def handle_client(self, client):
        """Xử lý tin nhắn từ một client"""
        while True:
            try:
                # Nhận tin nhắn từ client
                message = client.recv(1024)
                if message:
                    # Broadcast tin nhắn tới tất cả client khác
                    self.broadcast(message, client)
                else:
                    # Client ngắt kết nối
                    self.remove_client(client)
                    break
            except:
                # Lỗi khi nhận tin nhắn
                self.remove_client(client)
                break
    
    def start_server(self):
        """Khởi động server"""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen()
        
        print(f"[SERVER] Server đang chạy tại {self.host}:{self.port}")
        print("[SERVER] Đang chờ kết nối...")
        
        while True:
            try:
                # Chấp nhận kết nối từ client
                client, address = server.accept()
                print(f"[SERVER] Kết nối từ {str(address)}")
                
                # Yêu cầu client gửi nickname
                client.send("NICK".encode('utf-8'))
                nickname = client.recv(1024).decode('utf-8')
                
                # Thêm client vào danh sách
                self.clients.append(client)
                self.nicknames.append(nickname)
                
                print(f"[SERVER] {nickname} đã tham gia chat room")
                
                # Thông báo cho tất cả client về thành viên mới
                join_message = f"{nickname} đã tham gia chat room!".encode('utf-8')
                self.broadcast(join_message)
                
                # Gửi thông báo chào mừng cho client mới
                welcome_message = f"Chào mừng {nickname}! Bạn đã kết nối thành công.".encode('utf-8')
                client.send(welcome_message)
                
                # Tạo thread để xử lý client này
                client_thread = threading.Thread(target=self.handle_client, args=(client,))
                client_thread.daemon = True
                client_thread.start()
                
            except Exception as e:
                print(f"[SERVER] Lỗi: {e}")
                break

if __name__ == "__main__":
    # Tạo và khởi động server
    chat_server = ChatServer(
        host = '0.0.0.0',
        port = 8204
    )
    try:
        chat_server.start_server()
    except KeyboardInterrupt:
        print("\n[SERVER] Server đang tắt...")
    except Exception as e:
        print(f"[SERVER] Lỗi khi khởi động server: {e}")