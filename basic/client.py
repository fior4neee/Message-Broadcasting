import socket
import threading

class ChatClient:
    def __init__(self, host='localhost', port=12345):
        self.host = host
        self.port = port
        self.nickname = ""
        self.client_socket = None
        self.running = False
        
    def receive_messages(self):
        """Nhận tin nhắn từ server"""
        while self.running:
            try:
                message = self.client_socket.recv(1024).decode('utf-8')
                
                # Nếu server yêu cầu nickname
                if message == "NICK":
                    self.client_socket.send(self.nickname.encode('utf-8'))
                else:
                    # In tin nhắn ra màn hình
                    print(message)
                    
            except Exception as e:
                if self.running:
                    print(f"[CLIENT] Lỗi khi nhận tin nhắn: {e}")
                break
    
    def send_messages(self):
        """Gửi tin nhắn tới server"""
        while self.running:
            try:
                message = input("")
                
                # Kiểm tra lệnh thoát
                if message.lower() in ['/quit', '/exit', '/q']:
                    self.disconnect()
                    break
                
                # Gửi tin nhắn với định dạng: [nickname]: message
                full_message = f"[{self.nickname}]: {message}"
                self.client_socket.send(full_message.encode('utf-8'))
                
            except Exception as e:
                if self.running:
                    print(f"[CLIENT] Lỗi khi gửi tin nhắn: {e}")
                break
    
    def connect_to_server(self):
        """Kết nối tới server"""
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.host, self.port))
            self.running = True
            
            print(f"[CLIENT] Đã kết nối tới server {self.host}:{self.port}")
            
            # Tạo thread để nhận tin nhắn
            receive_thread = threading.Thread(target=self.receive_messages)
            receive_thread.daemon = True
            receive_thread.start()
            
            # Tạo thread để gửi tin nhắn
            send_thread = threading.Thread(target=self.send_messages)
            send_thread.daemon = True
            send_thread.start()
            
            # Giữ chương trình chạy
            send_thread.join()
            
        except Exception as e:
            print(f"[CLIENT] Không thể kết nối tới server: {e}")
    
    def disconnect(self):
        """Ngắt kết nối khỏi server"""
        print("\n[CLIENT] Đang ngắt kết nối...")
        self.running = False
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass

def main():
    print("=== CHAT CLIENT ===")
    
    # Nhập nickname
    nickname = input("Nhập nickname của bạn: ")
    if not nickname.strip():
        print("Nickname không được để trống!")
        return
    
    # Tùy chọn server (mặc định localhost:12345)
    server_input = input("Nhập địa chỉ server (Enter để dùng localhost:12345): ")
    
    if server_input.strip():
        try:
            if ':' in server_input:
                host, port = server_input.split(':')
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
    
    # Tạo client và kết nối
    client = ChatClient(host, port)
    client.nickname = nickname
    
    print(f"\nĐang kết nối tới {host}:{port}...")
    print("Gõ tin nhắn và nhấn Enter để gửi")
    print("Gõ /quit, /exit hoặc /q để thoát")
    print("-" * 40)
    
    try:
        client.connect_to_server()
    except KeyboardInterrupt:
        print("\n[CLIENT] Ngắt kết nối bởi người dùng")
        client.disconnect()

if __name__ == "__main__":
    main()