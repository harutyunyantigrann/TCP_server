import socket
import threading
from jinja2 import Environment, FileSystemLoader
import logging
import psycopg2
from urllib.parse import parse_qs, unquote_plus
import uuid

# --- Logging configuration ---
logging.basicConfig(
    filename="server.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filemode="a"
)

# --- Session storage ---
sessions = {}

# --- Database functions ---

def get_messages(username):
    """Fetch all messages for a given username from the database"""
    try:
        with psycopg2.connect(
            dbname="tcp_server",
            user="postgres",
            password="test_pass_for_tcp",
            host="localhost",
            port="5432"
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT sender, content, created_at FROM messages WHERE receiver = %s", (username,))
                messages = cur.fetchall()
                logging.debug(f"Retrieved {len(messages)} messages for user {username}")
                return messages
    except Exception as e:
        logging.exception("Exception occurred while fetching messages")

def insert_messages(sender, receiver, content):
    """Insert a new message into the database"""
    try:
        with psycopg2.connect(
            dbname="tcp_server",
            user="postgres",
            password="test_pass_for_tcp",
            host="localhost",
            port="5432"
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO messages (sender, receiver, content) VALUES (%s, %s, %s)", (sender, receiver, content))
                conn.commit()
                logging.info(f"Message inserted from {sender} to {receiver}")
    except Exception as e:
        logging.exception("Exception occurred while inserting message")

def check_username(username):
    """Check if the username exists in the auth table"""
    try:
        with psycopg2.connect(
            dbname="tcp_server",
            user="postgres",
            password="test_pass_for_tcp",
            host="localhost",
            port="5432"
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM auth WHERE username = %s", (username,))
                data = cur.fetchone()
                exists = data is not None
                logging.debug(f"Username check for '{username}': {exists}")
                return exists
    except Exception as e:
        logging.exception(f"Exception occurred while checking username: {username}")
        return False

def insert_credentials(username, password):
    """Insert a new user into the auth table"""
    try:
        with psycopg2.connect(
            dbname="tcp_server",
            user="postgres",
            password="test_pass_for_tcp",
            host="localhost",
            port="5432"
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO auth (username,password) VALUES (%s,%s)", (username, password))
                conn.commit()
                logging.info(f"Successfully registered user: {username}")
    except Exception as e:
        logging.exception(f"Exception occurred while inserting credentials for username: {username}")

def check_credentials(username, password):
    """Check if provided credentials match a record in auth table"""
    try:
        with psycopg2.connect(
            dbname="tcp_server",
            user="postgres",
            password="test_pass_for_tcp",
            host="localhost",
            port="5432"
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM auth WHERE username=%s AND password=%s", (username, password))
                result = cur.fetchone()
                valid = result is not None
                logging.debug(f"Credentials check for '{username}': {valid}")
                return valid
    except Exception as e:
        logging.exception(f"Exception occurred while checking credentials for username: {username}")
        return False

# --- Jinja template functions ---

def auth_jinja(error_msg=None):
    """Render the login/signup page with optional error"""
    env = Environment(loader=FileSystemLoader('Templates'))
    html = env.get_template('auth.html')
    logging.debug(f"Rendering login page. Error: {error_msg}")
    return html.render(error=error_msg)

def profile_jinja(_username, _rows, _error=None, _success=None):
    """Render the profile page with messages and optional error/success messages"""
    env = Environment(loader=FileSystemLoader('Templates'))
    body = env.get_template('profile.html')
    _messages = []
    for message in _rows:
        _messages.append({"from": message[0], 
                          "text": message[1], 
                          "time":message[2].strftime("%Y-%m-%d %H:%M")})
    logging.debug(f"Rendering profile page for user {_username}. Error: {_error}, Success: {_success}")
    return body.render(username=_username, messages=_messages, error=_error, success=_success)

def notfound_jinja():
    """Render a 404 page"""
    env = Environment(loader=FileSystemLoader('Templates'))
    html = env.get_template('404.html')
    logging.debug("Rendering 404 page")
    return html.render()

# --- HTTP request parsing ---

def get_data(client_socket, client_address):
    """Receive HTTP headers and body from client"""
    data = b""
    body = b""
    while b"\r\n\r\n" not in data:
        temp = client_socket.recv(4096)
        if temp:
            data += temp
        else:
            break

    headers_list, body = data.split(b"\r\n\r\n", 1)
    headers_lines = headers_list.split(b"\r\n")
    method, path, version = headers_lines[0].split(b" ")
    headers_list = headers_lines[1:]
    headers = {}
    for header in headers_list:
        if b":" in header:
            key, value = header.split(b":", 1)
            headers[key.decode().strip().lower()] = value.decode().strip()
    content_length = int(headers.get("content-length", 0))

    if content_length > 1048576:
        # If body too large, close connection
        response = "HTTP/1.1 413 Payload Too Large\r\nContent-Length: 0\r\n\r\n"
        logging.critical(f"Payload too large from {client_address[0]}")
        client_socket.sendall(response.encode())
        client_socket.close()
        return

    while len(body) < content_length:
        temp = client_socket.recv(4096)
        if temp:
            body += temp
        else:
            break

    logging.debug(f"Received data from {client_address[0]}: {method.decode()} {path.decode()}")
    return method.decode(), path.decode(), version.decode(), headers, body.decode()

# --- Main connection handler ---

def connect(client_socket, client_address):
    """Handle a single client connection"""
    try:
        logging.info(f"Client connected {client_address[0]}:{client_address[1]}")
        data = get_data(client_socket, client_address)
        if data is None:
            logging.error("No data received from client")
            return
        method, path, version, headers, body = data
        logging.info(f"Request {method} {path} from {client_address[0]}")

        # --- GET /login ---
        if method == "GET" and path == "/login":
            body = auth_jinja().encode("utf-8")
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html\r\n"
                f"Content-Length: {len(body)}\r\n\r\n"
            ).encode("utf-8") + body
            logging.info(f"Serving login page to {client_address[0]}")

        # --- POST /signup ---
        elif method == "POST" and path == "/signup":
            parsed_credentials = parse_qs(body)
            username = parsed_credentials.get('username', [None])[0]
            password = parsed_credentials.get('password', [None])[0]
            logging.debug(f"Signup attempt: {username}")

            if check_username(username):
                body = auth_jinja(error_msg="This username is already taken").encode("utf-8")
                response = (
                    "HTTP/1.1 400 Bad Request\r\n"
                    "Content-Type: text/html\r\n"
                    f"Content-Length: {len(body)}\r\n\r\n"
                ).encode("utf-8") + body
                client_socket.sendall(response)
                return
            elif len(password) < 8:
                body = auth_jinja(error_msg="Password can`t be less than 8 symbols").encode("utf-8")
                response = (
                    "HTTP/1.1 400 Bad Request\r\n"
                    "Content-Type: text/html\r\n"
                    f"Content-Length: {len(body)}\r\n\r\n"
                ).encode("utf-8") + body
                client_socket.sendall(response)
                return
            else:
                insert_credentials(username, password)
                body = auth_jinja(error_msg="You are registered successfully!").encode("utf-8")
                response = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: text/html\r\n"
                    f"Content-Length: {len(body)}\r\n\r\n"
                ).encode("utf-8") + body
                logging.info(f"User {username} successfully registered")

        # --- POST /signin ---
        elif method == "POST" and path == "/signin":
            parsed_credentials = parse_qs(body)
            username = parsed_credentials.get('username', [None])[0]
            password = parsed_credentials.get('password', [None])[0]
            logging.debug(f"Signin attempt: {username}")

            if username is None or password is None:
                body = auth_jinja("Username or password can't be empty!").encode("utf-8")
                response = (
                    "HTTP/1.1 400 Bad Request\r\n"
                    "Content-Type: text/html\r\n"
                    f"Content-Length: {len(body)}\r\n\r\n"
                ).encode("utf-8") + body
                client_socket.sendall(response)
                return

            if not check_credentials(username, password):
                body = auth_jinja(error_msg="Invalid username or password").encode("utf-8")
                response = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: text/html\r\n"
                    f"Content-Length: {len(body)}\r\n\r\n"
                ).encode("utf-8") + body
                client_socket.sendall(response)
                return

            # Successful login
            session_id = uuid.uuid4()
            sessions[session_id] = username
            body = profile_jinja(username, get_messages(username)).encode("utf-8")
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"Set-Cookie: session_id={session_id}; HttpOnly; Path=/\r\n\r\n"
            ).encode("utf-8") + body
            logging.info(f"User {username} logged in, session {session_id}")

        # --- POST /message ---
        elif method == "POST" and path == "/message":
            logging.debug(f"Message POST body: {body}")
            body_parsed = parse_qs(body)
            sender = body_parsed.get('from', [None])[0]
            receiver = body_parsed.get('to', [None])[0]
            content = body_parsed.get('text', [None])[0]
            messages = get_messages(sender)

            if not check_username(receiver):
                body = profile_jinja(sender, messages, "Receiver username not found").encode("utf-8")
                response = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: text/html\r\n"
                    f"Content-Length: {len(body)}\r\n\r\n"
                ).encode("utf-8") + body
                client_socket.sendall(response)
                logging.warning(f"Message failed: receiver {receiver} not found")
                client_socket.close()
                return

            insert_messages(sender, receiver, content)
            body = profile_jinja(sender, messages, None, "Message successfully sent!").encode("utf-8")
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html\r\n"
                f"Content-Length: {len(body)}\r\n\r\n"
            ).encode("utf-8") + body
            logging.info(f"Message sent from {sender} to {receiver}")

        # --- Default: 404 Not Found ---
        else:
            body = notfound_jinja().encode("utf-8")
            response = (
                "HTTP/1.1 404 Not Found\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Content-Type: text/html; charset=utf-8\r\n\r\n"
            ).encode("utf-8") + body
            logging.error(f"404 Not Found: {method} {path} from {client_address[0]}")

        client_socket.sendall(response)

    except Exception as e:
        logging.exception(f"Exception while handling client {client_address[0]}: {e}")

    finally:
        logging.info(f"Closing connection with {client_address[0]}")
        client_socket.close()

# --- Server main loop ---

try:
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(("127.0.0.1", 8080))
    server_socket.listen(5)
    logging.info("Server started on 127.0.0.1:8080")

    while True:
        client_socket, client_address = server_socket.accept()
        thread = threading.Thread(target=connect, args=(client_socket, client_address))
        thread.start()

except Exception as e:
    logging.exception(f"Fatal error in server socket: {e}")

finally:
    server_socket.close()
    logging.info("Server socket closed")
