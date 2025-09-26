#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <signal.h>
#include <stdint.h>
#include <ctype.h>
// gcc client.c -o client.exe -lws2_32
// gcc -std=c99 client.c -o client.exe -lws2_32 -static-libgcc
#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    #include <windows.h>
    #pragma comment(lib, "ws2_32.lib")
    #define close closesocket
    #define usleep(x) Sleep((x)/1000)
    typedef HANDLE pthread_t;
    typedef CRITICAL_SECTION pthread_mutex_t;
    
    int pthread_mutex_init(pthread_mutex_t* mutex, void* attr) {
        InitializeCriticalSection(mutex);
        return 0;
    }
    
    int pthread_mutex_lock(pthread_mutex_t* mutex) {
        EnterCriticalSection(mutex);
        return 0;
    }
    
    int pthread_mutex_unlock(pthread_mutex_t* mutex) {
        LeaveCriticalSection(mutex);
        return 0;
    }
    
    int pthread_mutex_destroy(pthread_mutex_t* mutex) {
        DeleteCriticalSection(mutex);
        return 0;
    }
    
    int pthread_create(pthread_t* thread, void* attr, void* (*func)(void*), void* arg) {
        *thread = CreateThread(NULL, 0, (LPTHREAD_START_ROUTINE)func, arg, 0, NULL);
        return *thread == NULL ? -1 : 0;
    }
    
    int pthread_detach(pthread_t thread) {
        CloseHandle(thread);
        return 0;
    }
    
#else
    #include <pthread.h>
    #include <unistd.h>
    #include <arpa/inet.h>
    #include <sys/socket.h>
    #include <netinet/in.h>
    #include <errno.h>
#endif

// Protocol constants
#define MAGIC 0xCAFE
#define VERSION 0x01
#define HEADER_SIZE 9

// Message types
#define LOGIN_REQUEST 0x01
#define LOGIN_RESPONSE 0x02
#define CHAT_MESSAGE 0x03
#define USER_JOIN 0x04
#define USER_LEAVE 0x05
#define USER_LIST 0x06
#define PING 0x07
#define PONG 0x08
#define MSG_ERROR 0x09  // Changed from ERROR to avoid Windows conflict

// Buffer sizes
#define MAX_NICKNAME_LEN 51
#define MAX_MESSAGE_LEN 1024
#define MAX_BUFFER_LEN 4096
#define MAX_USERS 100

// Protocol header structure
#pragma pack(push, 1)
typedef struct {
    uint16_t magic;
    uint8_t version;
    uint8_t reserved;
    uint8_t type;
    uint32_t length;
} protocol_header_t;
#pragma pack(pop)

// Simple JSON key-value structure
typedef struct {
    char key[64];
    char value[256];
} json_pair_t;

typedef struct {
    json_pair_t pairs[10];
    int count;
} simple_json_t;

// Client state
typedef struct {
    int socket_fd;
    char nickname[MAX_NICKNAME_LEN];
    char host[256];
    int port;
    int running;
    int logged_in;
    char users[MAX_USERS][MAX_NICKNAME_LEN];
    int user_count;
    pthread_mutex_t users_mutex;
    uint8_t receive_buffer[MAX_BUFFER_LEN * 2];
    int buffer_len;
    pthread_mutex_t buffer_mutex;
} chat_client_t;

// Global client instance
static chat_client_t client = {0};

// Function prototypes
void signal_handler(int sig);
void format_timestamp(time_t timestamp, char* buffer, size_t buffer_size);
void get_current_timestamp(char* buffer, size_t buffer_size);
simple_json_t parse_simple_json(const char* json_str);
char* get_json_value(simple_json_t* json, const char* key);
int get_json_bool(simple_json_t* json, const char* key);
double get_json_double(simple_json_t* json, const char* key);
int pack_message(uint8_t msg_type, const char* data, uint8_t* buffer, size_t buffer_size);
int unpack_message(const uint8_t* buffer, int buffer_len, int* offset, uint8_t* msg_type, char* data, size_t data_size);
int send_message(uint8_t msg_type, const char* data);
void handle_login_response(const char* data);
void handle_chat_message(const char* data);
void handle_user_join(const char* data);
void handle_user_leave(const char* data);
void handle_user_list(const char* data);
int handle_error(const char* data);
void handle_pong(const char* data);
void* receive_messages_thread(void* arg);
int handle_received_message(uint8_t msg_type, const char* data);
int send_chat_message(const char* message);
int login_to_server();
int send_ping();
char* process_command(const char* message);
void input_loop();
int connect_to_server();
void disconnect_client();
int init_networking();
void cleanup_networking();

// Initialize networking (Windows specific)
int init_networking() {
#ifdef _WIN32
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
        printf("[CLIENT] WSAStartup failed\n");
        return 0;
    }
#endif
    return 1;
}

// Cleanup networking
void cleanup_networking() {
#ifdef _WIN32
    WSACleanup();
#endif
}

// Signal handler for graceful shutdown
void signal_handler(int sig) {
    printf("\n[CLIENT] Nhận signal %d, đang thoát...\n", sig);
    client.running = 0;
    disconnect_client();
    cleanup_networking();
    exit(0);
}

// Format timestamp to HH:MM:SS string
void format_timestamp(time_t timestamp, char* buffer, size_t buffer_size) {
    struct tm* timeinfo = localtime(&timestamp);
    strftime(buffer, buffer_size, "%H:%M:%S", timeinfo);
}

// Get current timestamp as formatted string
void get_current_timestamp(char* buffer, size_t buffer_size) {
    time_t now = time(NULL);
    format_timestamp(now, buffer, buffer_size);
}

// Simple JSON parser - only handles basic key:value pairs
simple_json_t parse_simple_json(const char* json_str) {
    simple_json_t json = {0};
    char temp[1024];
    strncpy(temp, json_str, sizeof(temp) - 1);
    temp[sizeof(temp) - 1] = '\0';
    
    // Remove braces and quotes
    char* start = strchr(temp, '{');
    char* end = strrchr(temp, '}');
    if (!start || !end) return json;
    
    start++;
    *end = '\0';
    
    // Parse pairs
    char* pair = strtok(start, ",");
    while (pair && json.count < 10) {
        // Remove leading/trailing spaces
        while (*pair == ' ' || *pair == '\t') pair++;
        
        char* colon = strchr(pair, ':');
        if (colon) {
            *colon = '\0';
            char* key = pair;
            char* value = colon + 1;
            
            // Remove quotes
            if (*key == '"') key++;
            if (key[strlen(key)-1] == '"') key[strlen(key)-1] = '\0';
            if (*value == '"') value++;
            if (value[strlen(value)-1] == '"') value[strlen(value)-1] = '\0';
            
            // Remove spaces
            while (*value == ' ' || *value == '\t') value++;
            
            strncpy(json.pairs[json.count].key, key, sizeof(json.pairs[json.count].key) - 1);
            strncpy(json.pairs[json.count].value, value, sizeof(json.pairs[json.count].value) - 1);
            json.count++;
        }
        
        pair = strtok(NULL, ",");
    }
    
    return json;
}

// Get value from JSON by key
char* get_json_value(simple_json_t* json, const char* key) {
    for (int i = 0; i < json->count; i++) {
        if (strcmp(json->pairs[i].key, key) == 0) {
            return json->pairs[i].value;
        }
    }
    return NULL;
}

// Get boolean value from JSON
int get_json_bool(simple_json_t* json, const char* key) {
    char* value = get_json_value(json, key);
    if (value) {
        return (strcmp(value, "true") == 0 || strcmp(value, "1") == 0);
    }
    return 0;
}

// Get double value from JSON
double get_json_double(simple_json_t* json, const char* key) {
    char* value = get_json_value(json, key);
    if (value) {
        return atof(value);
    }
    return 0.0;
}

// Pack message according to protocol
int pack_message(uint8_t msg_type, const char* data, uint8_t* buffer, size_t buffer_size) {
    size_t data_len = strlen(data);
    if (HEADER_SIZE + data_len > buffer_size) {
        return -1;  // Buffer too small
    }
    
    protocol_header_t header;
    header.magic = htons(MAGIC);
    header.version = VERSION;
    header.reserved = 0;
    header.type = msg_type;
    header.length = htonl((uint32_t)data_len);
    
    memcpy(buffer, &header, HEADER_SIZE);
    memcpy(buffer + HEADER_SIZE, data, data_len);
    
    return HEADER_SIZE + (int)data_len;
}

// Unpack message from buffer
int unpack_message(const uint8_t* buffer, int buffer_len, int* offset, uint8_t* msg_type, char* data, size_t data_size) {
    if (buffer_len - *offset < HEADER_SIZE) {
        return 0;  // Not enough data for header
    }
    
    const protocol_header_t* header = (const protocol_header_t*)(buffer + *offset);
    uint16_t magic = ntohs(header->magic);
    uint32_t length = ntohl(header->length);
    
    if (magic != MAGIC) {
        printf("[CLIENT] Invalid magic number: 0x%04X\n", magic);
        return -1;
    }
    
    if (header->version != VERSION) {
        printf("[CLIENT] Unsupported version: %d\n", header->version);
        return -1;
    }
    
    if (buffer_len - *offset < HEADER_SIZE + (int)length) {
        return 0;  // Not enough data for complete message
    }
    
    if (length >= data_size) {
        printf("[CLIENT] Message too large: %u bytes\n", length);
        return -1;
    }
    
    *msg_type = header->type;
    memcpy(data, buffer + *offset + HEADER_SIZE, length);
    data[length] = '\0';  // Null terminate
    
    *offset += HEADER_SIZE + length;
    return 1;  // Success
}

// Send message to server
int send_message(uint8_t msg_type, const char* data) {
    uint8_t buffer[MAX_BUFFER_LEN];
    int message_len = pack_message(msg_type, data, buffer, sizeof(buffer));
    
    if (message_len < 0) {
        printf("[CLIENT] Lỗi đóng gói message\n");
        return 0;
    }
    
    int sent = send(client.socket_fd, (const char*)buffer, message_len, 0);
    if (sent != message_len) {
#ifdef _WIN32
        printf("[CLIENT] Lỗi gửi message: %d\n", WSAGetLastError());
#else
        printf("[CLIENT] Lỗi gửi message: %s\n", strerror(errno));
#endif
        return 0;
    }
    
    return 1;
}

// Handle login response
void handle_login_response(const char* data) {
    simple_json_t json = parse_simple_json(data);
    
    if (get_json_bool(&json, "success")) {
        client.logged_in = 1;
        char timestamp[16];
        time_t t = (time_t)get_json_double(&json, "timestamp");
        if (t == 0) t = time(NULL);
        format_timestamp(t, timestamp, sizeof(timestamp));
        
        char* message = get_json_value(&json, "message");
        printf("[%s] %s\n", timestamp, message ? message : "Đăng nhập thành công!");
        printf("--------------------------------------------------\n");
    } else {
        char* message = get_json_value(&json, "message");
        printf("[ERROR] Đăng nhập thất bại: %s\n", message ? message : "Unknown error");
    }
}

// Handle chat message
void handle_chat_message(const char* data) {
    simple_json_t json = parse_simple_json(data);
    char* nickname = get_json_value(&json, "nickname");
    char* message = get_json_value(&json, "message");
    
    if (nickname && message && strcmp(nickname, client.nickname) != 0) {
        char timestamp[16];
        time_t t = (time_t)get_json_double(&json, "timestamp");
        if (t == 0) t = time(NULL);
        format_timestamp(t, timestamp, sizeof(timestamp));
        
        printf("[%s] %s: %s\n", timestamp, nickname, message);
    }
}

// Handle user join notification
void handle_user_join(const char* data) {
    simple_json_t json = parse_simple_json(data);
    char* nickname = get_json_value(&json, "nickname");
    
    if (nickname) {
        char timestamp[16];
        time_t t = (time_t)get_json_double(&json, "timestamp");
        if (t == 0) t = time(NULL);
        format_timestamp(t, timestamp, sizeof(timestamp));
        
        printf("[%s] >>> %s đã tham gia chat room <<<\n", timestamp, nickname);
    }
}

// Handle user leave notification
void handle_user_leave(const char* data) {
    simple_json_t json = parse_simple_json(data);
    char* nickname = get_json_value(&json, "nickname");
    
    if (nickname) {
        char timestamp[16];
        time_t t = (time_t)get_json_double(&json, "timestamp");
        if (t == 0) t = time(NULL);
        format_timestamp(t, timestamp, sizeof(timestamp));
        
        printf("[%s] <<< %s đã rời khỏi chat room >>>\n", timestamp, nickname);
    }
}

// Handle user list
void handle_user_list(const char* data) {
    simple_json_t json = parse_simple_json(data);
    char* users = get_json_value(&json, "users");
    int count = (int)get_json_double(&json, "count");
    
    pthread_mutex_lock(&client.users_mutex);
    client.user_count = 0;
    
    // Parse user list (format: "user1,user2,user3")
    if (users) {
        char temp[1024];
        strncpy(temp, users, sizeof(temp) - 1);
        temp[sizeof(temp) - 1] = '\0';
        
        char* user = strtok(temp, ",");
        while (user && client.user_count < MAX_USERS) {
            strncpy(client.users[client.user_count], user, MAX_NICKNAME_LEN - 1);
            client.users[client.user_count][MAX_NICKNAME_LEN - 1] = '\0';
            client.user_count++;
            user = strtok(NULL, ",");
        }
        
        printf("[INFO] Có %d người trong chat room: %s\n", count, users);
    }
    
    pthread_mutex_unlock(&client.users_mutex);
}

// Handle error message
int handle_error(const char* data) {
    simple_json_t json = parse_simple_json(data);
    int error_code = (int)get_json_double(&json, "error_code");
    char* error_message = get_json_value(&json, "error_message");
    
    char timestamp[16];
    time_t t = (time_t)get_json_double(&json, "timestamp");
    if (t == 0) t = time(NULL);
    format_timestamp(t, timestamp, sizeof(timestamp));
    
    printf("[%s] ERROR %d: %s\n", timestamp, error_code, 
           error_message ? error_message : "Unknown error");
    
    // If nickname exists error, signal to retry
    if (error_code == 409) {
        return 0;  // Signal to retry login
    }
    
    return 1;
}

// Handle pong response
void handle_pong(const char* data) {
    // Can be used for ping time measurement
}

// Thread function for receiving messages
void* receive_messages_thread(void* arg) {
    char buffer[MAX_BUFFER_LEN];
    
    while (client.running) {
        int received = recv(client.socket_fd, buffer, sizeof(buffer), 0);
        if (received <= 0) {
            if (client.running) {
                printf("[CLIENT] Mất kết nối với server\n");
            }
            break;
        }
        
        pthread_mutex_lock(&client.buffer_mutex);
        
        // Add to receive buffer
        if (client.buffer_len + received < (int)sizeof(client.receive_buffer)) {
            memcpy(client.receive_buffer + client.buffer_len, buffer, received);
            client.buffer_len += received;
        } else {
            printf("[CLIENT] Buffer overflow, clearing buffer\n");
            client.buffer_len = 0;
            pthread_mutex_unlock(&client.buffer_mutex);
            continue;
        }
        
        // Process all complete messages
        int offset = 0;
        while (offset < client.buffer_len) {
            uint8_t msg_type;
            char msg_data[MAX_MESSAGE_LEN];
            
            int result = unpack_message(client.receive_buffer, client.buffer_len, &offset, &msg_type, msg_data, sizeof(msg_data));
            
            if (result == 1) {
                handle_received_message(msg_type, msg_data);
            } else if (result == 0) {
                break;  // Need more data
            } else {
                // Error, clear buffer
                client.buffer_len = 0;
                offset = 0;
                break;
            }
        }
        
        // Remove processed data from buffer
        if (offset > 0) {
            memmove(client.receive_buffer, client.receive_buffer + offset, client.buffer_len - offset);
            client.buffer_len -= offset;
        }
        
        pthread_mutex_unlock(&client.buffer_mutex);
    }
    
    client.running = 0;
    return NULL;
}

// Handle received message by type
int handle_received_message(uint8_t msg_type, const char* data) {
    switch (msg_type) {
        case LOGIN_RESPONSE:
            handle_login_response(data);
            break;
            
        case CHAT_MESSAGE:
            handle_chat_message(data);
            break;
            
        case USER_JOIN:
            handle_user_join(data);
            break;
            
        case USER_LEAVE:
            handle_user_leave(data);
            break;
            
        case USER_LIST:
            handle_user_list(data);
            break;
            
        case MSG_ERROR:
            return handle_error(data);
            
        case PONG:
            handle_pong(data);
            break;
            
        default:
            printf("[CLIENT] Unknown message type: %d\n", msg_type);
            break;
    }
    
    return 1;
}

// Send chat message
int send_chat_message(const char* message) {
    if (client.logged_in && strlen(message) > 0) {
        if (send_message(CHAT_MESSAGE, message)) {
            char timestamp[16];
            get_current_timestamp(timestamp, sizeof(timestamp));
            printf("[%s] %s: %s\n", timestamp, client.nickname, message);
            return 1;
        }
    }
    return 0;
}

// Login to server
int login_to_server() {
    const int max_retries = 3;
    
    for (int attempt = 0; attempt < max_retries; attempt++) {
        if (attempt > 0) {
            printf("\nThử lại lần %d/%d\n", attempt + 1, max_retries);
        }
        
        if (send_message(LOGIN_REQUEST, client.nickname)) {
            // Wait for response (timeout after 5 seconds)
            time_t start_time = time(NULL);
            while (time(NULL) - start_time < 5) {
                if (client.logged_in) {
                    return 1;
                }
                usleep(100000);  // 100ms
            }
            
            if (!client.logged_in) {
                printf("[ERROR] Timeout waiting for login response\n");
            }
        } else {
            printf("[ERROR] Không thể gửi login request\n");
        }
    }
    
    return 0;
}

// Send ping message
int send_ping() {
    char ping_data[128];
    snprintf(ping_data, sizeof(ping_data), "{\"timestamp\":%.0f}", (double)time(NULL));
    return send_message(PING, ping_data);
}

// Process special commands
char* process_command(const char* message) {
    static char result[16];
    
    if (strlen(message) == 0 || message[0] != '/') {
        strcpy(result, "");
        return result;
    }
    
    char cmd[64];
    sscanf(message, "%63s", cmd);
    
    // Convert to lowercase
    for (int i = 0; cmd[i]; i++) {
        cmd[i] = (char)tolower(cmd[i]);
    }
    
    if (strcmp(cmd, "/quit") == 0 || strcmp(cmd, "/exit") == 0 || strcmp(cmd, "/q") == 0) {
        strcpy(result, "quit");
        return result;
    }
    
    if (strcmp(cmd, "/ping") == 0) {
        if (send_ping()) {
            printf("[INFO] Ping sent\n");
        }
        strcpy(result, "continue");
        return result;
    }
    
    if (strcmp(cmd, "/users") == 0 || strcmp(cmd, "/list") == 0) {
        pthread_mutex_lock(&client.users_mutex);
        if (client.user_count > 0) {
            printf("[INFO] Users online (%d): ", client.user_count);
            for (int i = 0; i < client.user_count; i++) {
                if (i > 0) printf(", ");
                printf("%s", client.users[i]);
            }
            printf("\n");
        } else {
            printf("[INFO] Không có thông tin danh sách users\n");
        }
        pthread_mutex_unlock(&client.users_mutex);
        strcpy(result, "continue");
        return result;
    }
    
    if (strcmp(cmd, "/help") == 0) {
        printf("\n=== COMMANDS ===\n");
        printf("/quit, /exit, /q - Thoát khỏi chat\n");
        printf("/ping - Test connection\n");
        printf("/users, /list - Xem danh sách users\n");
        printf("/help - Hiển thị help\n");
        printf("===============\n\n");
        strcpy(result, "continue");
        return result;
    }
    
    printf("[INFO] Lệnh không hợp lệ: %s. Gõ /help để xem danh sách lệnh\n", cmd);
    strcpy(result, "continue");
    return result;
}

// Main input loop
void input_loop() {
    char line[MAX_MESSAGE_LEN];
    
    while (client.running) {
        if (client.logged_in) {
            if (fgets(line, sizeof(line), stdin)) {
                // Remove newline
                line[strcspn(line, "\n")] = '\0';
                
                if (strlen(line) > 0) {
                    char* cmd_result = process_command(line);
                    
                    if (strcmp(cmd_result, "quit") == 0) {
                        break;
                    } else if (strcmp(cmd_result, "continue") == 0) {
                        continue;
                    }
                    
                    // Send regular message
                    if (!send_chat_message(line)) {
                        printf("[ERROR] Không thể gửi tin nhắn\n");
                    }
                }
            } else {
                break;  // EOF or error
            }
        } else {
            usleep(100000);  // Wait for login
        }
    }
    
    disconnect_client();
}

// Connect to server and run client
int connect_to_server() {
    struct sockaddr_in server_addr;
    
    // Create socket
    client.socket_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (client.socket_fd < 0) {
#ifdef _WIN32
        printf("[CLIENT] Không thể tạo socket: %d\n", WSAGetLastError());
#else
        printf("[CLIENT] Không thể tạo socket: %s\n", strerror(errno));
#endif
        return 0;
    }
    
    // Set up server address
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons((uint16_t)client.port);
    
    if (inet_pton(AF_INET, client.host, &server_addr.sin_addr) <= 0) {
        printf("[CLIENT] Địa chỉ server không hợp lệ: %s\n", client.host);
        close(client.socket_fd);
        return 0;
    }
    
    // Connect to server
    if (connect(client.socket_fd, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {
#ifdef _WIN32
        printf("[CLIENT] Không thể kết nối đến server: %d\n", WSAGetLastError());
#else
        printf("[CLIENT] Không thể kết nối đến server: %s\n", strerror(errno));
#endif
        close(client.socket_fd);
        return 0;
    }
    
    client.running = 1;
    
    printf("[CLIENT] Đã kết nối tới server %s:%d\n", client.host, client.port);
    
    // Start receive thread
    pthread_t receive_thread;
    if (pthread_create(&receive_thread, NULL, receive_messages_thread, NULL) != 0) {
        printf("[CLIENT] Không thể tạo receive thread\n");
        disconnect_client();
        return 0;
    }
    pthread_detach(receive_thread);
    
    // Login
    if (login_to_server()) {
        printf("Bạn có thể bắt đầu chat! Gõ /help để xem lệnh hỗ trợ\n");
        
        // Start input loop
        input_loop();
        return 1;
    } else {
        printf("[ERROR] Không thể đăng nhập\n");
        disconnect_client();
        return 0;
    }
}

// Disconnect from server
void disconnect_client() {
    printf("\n[CLIENT] Đang ngắt kết nối...\n");
    client.running = 0;
    client.logged_in = 0;
    
    if (client.socket_fd >= 0) {
        close(client.socket_fd);
        client.socket_fd = -1;
    }
}

int main() {
    // Initialize networking
    if (!init_networking()) {
        return 1;
    }
    
    // Initialize client
    memset(&client, 0, sizeof(client));
    client.socket_fd = -1;
    strcpy(client.host, "192.168.1.116");
    client.port = 12345;
    
    // Initialize mutexes
    pthread_mutex_init(&client.users_mutex, NULL);
    pthread_mutex_init(&client.buffer_mutex, NULL);
    
    // Set up signal handlers
    signal(SIGINT, signal_handler);
    
    printf("=== CHAT CLIENT (Improved Protocol) ===\n");
    printf("Protocol version: %d\n", VERSION);
    
    // Input nickname
    while (1) {
        printf("Nhập nickname của bạn: ");
        fflush(stdout);
        
        if (fgets(client.nickname, sizeof(client.nickname), stdin)) {
            // Remove newline and trim spaces
            client.nickname[strcspn(client.nickname, "\n")] = '\0';
            
            // Simple trim
            char* start = client.nickname;
            while (*start == ' ' || *start == '\t') start++;
            
            char* end = start + strlen(start) - 1;
            while (end > start && (*end == ' ' || *end == '\t')) *end-- = '\0';
            
            if (start != client.nickname) {
                memmove(client.nickname, start, strlen(start) + 1);
            }
            
            if (strlen(client.nickname) > 0 && strlen(client.nickname) <= 50) {
                break;
            }
        }
        
        printf("Nickname không được để trống và không quá 50 ký tự!\n");
    }
    
    // Server settings
    printf("Nhập địa chỉ server (Enter cho %s:%d): ", client.host, client.port);
    fflush(stdout);
    
    char server_input[256];
    if (fgets(server_input, sizeof(server_input), stdin)) {
        server_input[strcspn(server_input, "\n")] = '\0';
        
        if (strlen(server_input) > 0) {
            char* colon = strchr(server_input, ':');
            if (colon) {
                *colon = '\0';
                strcpy(client.host, server_input);
                client.port = atoi(colon + 1);
                if (client.port <= 0 || client.port > 65535) {
                    printf("Port không hợp lệ! Sử dụng mặc định.\n");
                    strcpy(client.host, "192.168.1.116");
                    client.port = 12345;
                }
            } else {
                strcpy(client.host, server_input);
            }
        }
    }
    
    printf("\nĐang kết nối tới %s:%d...\n", client.host, client.port);
    printf("--------------------------------------------------\n");
    
    // Connect and run
    int result = connect_to_server();
    
    // Cleanup
    pthread_mutex_destroy(&client.users_mutex);
    pthread_mutex_destroy(&client.buffer_mutex);
    cleanup_networking();
    
    return result ? 0 : 1;
}