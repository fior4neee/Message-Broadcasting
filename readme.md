# Chat Protocol Documentation

## Tổng quan

Đây là tài liệu mô tả giao thức chat được thiết kế cho ứng dụng message broadcasting. Giao thức này cho phép nhiều client kết nối đến server và chat với nhau trong thời gian thực.

## 1. Thiết kế Giao thức

### 1.1 Cấu trúc Message

Mỗi message được cấu trúc theo format sau:

```
| Magic (2 bytes) | Version (1 byte) | Reserved (1 byte) | Type (1 byte) | Length (4 bytes) | Data (variable) |
```

- **Magic Number**: `0xCAFE` - Nhận diện protocol
- **Version**: `0x01` - Phiên bản hiện tại
- **Reserved**: `0x00` - Dành cho tương lai
- **Type**: Loại message (1-9)
- **Length**: Độ dài phần Data (bytes)
- **Data**: Nội dung message (JSON hoặc string)

### 1.2 Message Types

| Type | Tên | Mô tả |
|------|-----|-------|
| 0x01 | LOGIN_REQUEST | Yêu cầu đăng nhập |
| 0x02 | LOGIN_RESPONSE | Phản hồi đăng nhập |
| 0x03 | CHAT_MESSAGE | Tin nhắn chat |
| 0x04 | USER_JOIN | Thông báo user tham gia |
| 0x05 | USER_LEAVE | Thông báo user rời đi |
| 0x06 | USER_LIST | Danh sách users online |
| 0x07 | PING | Kiểm tra kết nối |
| 0x08 | PONG | Phản hồi ping |
| 0x09 | ERROR | Thông báo lỗi |

## 2. Quy trình Giao tiếp

### 2.1 Kết nối và Đăng nhập

```
Client                          Server
  |                              |
  |----> TCP Connect ----------->|
  |----> LOGIN_REQUEST --------->|
  |      (nickname)              |
  |                              |
  |<---- LOGIN_RESPONSE ---------|
  |      (success/error)         |
  |                              |
  |<---- USER_LIST --------------|
  |      (danh sách users)       |
  |                              |
  |<---- USER_JOIN (broadcast)---|
  |      (thông báo tới all)     |
```

### 2.2 Chat Flow

```
Client A                 Server                 Client B,C,D...
   |                      |                         |
   |---> CHAT_MESSAGE --->|                         |
   |                      |---> CHAT_MESSAGE ------>|
   |                      |     (broadcast)         |
   |<--- CHAT_MESSAGE ----|                         |
   |     (echo back)      |                         |
```

### 2.3 Ngắt kết nối

```
Client                          Server
  |                              |
  |----> Disconnect ------------>|
  |                              |
  |                              |---> USER_LEAVE -----> All Clients
  |                              |     (broadcast)
  |                              |
  |                              |---> USER_LIST ------> All Clients
  |                              |     (updated list)
```

## 3. Data Formats

### 3.1 LOGIN_REQUEST
```
Type: 0x01
Data: "nickname_string"
```

### 3.2 LOGIN_RESPONSE
```json
{
  "success": true,
  "message": "Chào mừng john!",
  "timestamp": 1234567890
}
```

### 3.3 CHAT_MESSAGE
```json
{
  "nickname": "john",
  "message": "Hello everyone!",
  "timestamp": 1234567890
}
```

### 3.4 USER_JOIN/USER_LEAVE
```json
{
  "nickname": "alice",
  "message": "alice đã tham gia chat room",
  "timestamp": 1234567890
}
```

### 3.5 USER_LIST
```json
{
  "users": ["john", "alice", "bob"],
  "count": 3
}
```

### 3.6 ERROR
```json
{
  "error_code": 409,
  "error_message": "Nickname đã tồn tại",
  "timestamp": 1234567890
}
```

## 4. Error Codes

| Code | Tên | Mô tả |
|------|-----|-------|
| 400 | BAD_REQUEST | Request không hợp lệ |
| 401 | UNAUTHORIZED | Chưa đăng nhập |
| 409 | NICKNAME_EXISTS | Nickname đã tồn tại |
| 500 | SERVER_ERROR | Lỗi server |

## 5. Tính năng Client

### 5.1 Commands
- `/quit`, `/exit`, `/q` - Thoát khỏi chat
- `/ping` - Test connection với server
- `/users`, `/list` - Hiển thị danh sách users
- `/help` - Hiển thị help

### 5.2 Features
- Hiển thị timestamp cho mọi message
- Thông báo real-time khi user join/leave
- Auto-retry khi nickname trùng
- Xử lý mất kết nối gracefully

## 6. Tính năng Server

### 6.1 Multi-threading
- Mỗi client được xử lý bởi 1 thread riêng
- Thread-safe với locks cho shared data
- Automatic cleanup khi client disconnect

### 6.2 User Management
```python
clients = {
    client_socket: {
        "nickname": "john",
        "joined_at": 1234567890,
        "address": ("192.168.1.1", 12345)
    }
}
```

### 6.3 Broadcasting
- Message được broadcast tới tất cả clients
- Exclude sender để tránh duplicate
- Automatic cleanup cho disconnected clients

## 7. Cách sử dụng

### 7.1 Chạy Server
```bash
python server.py
```

Server sẽ lắng nghe tại `localhost:12345` theo mặc định.

### 7.2 Chạy Client
```bash
python client.py
```

Nhập nickname và bắt đầu chat!

### 7.3 Multiple Clients
Có thể chạy nhiều client instances để test:
```bash
# Terminal 1
python client.py

# Terminal 2  
python client.py

# Terminal 3
python client.py
```

## 8. Xử lý Lỗi

### 8.1 Network Errors
- Auto-retry cho connection timeout
- Graceful handling cho broken connections
- Buffer management cho incomplete messages

### 8.2 Protocol Errors
- Validation cho magic number và version
- Error response cho invalid message types
- Length validation để tránh buffer overflow

### 8.3 Application Errors
- Nickname conflict handling
- Input validation
- Server shutdown handling

## 9. Bảo mật

### 9.1 Hiện tại
- Basic input validation
- Nickname sanitization
- Length limits cho messages

### 9.2 Có thể cải thiện
- TLS/SSL encryption
- Authentication tokens
- Rate limiting
- Message signing

## 10. Performance

### 10.1 Optimizations
- Binary protocol thay vì text
- JSON compression cho large messages
- Connection pooling
- Message batching

### 10.2 Scalability
- Có thể handle ~100 concurrent users
- Memory usage tỷ lệ với số users
- CPU usage chủ yếu từ threading overhead

---

*Tài liệu này mô tả implementation hiện tại của chat protocol. Để biết thêm chi tiết, xem source code trong `server.py` và `client.py`.*