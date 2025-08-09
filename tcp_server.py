import socket
import threading
from jinja2 import Environment, FileSystemLoader
import logging
logging.basicConfig(
    filename="server.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filemode="a"
)
sessions = {}
def auth_jinja(error_msg=None):
    env = Environment(loader=FileSystemLoader('Templates'))
    html = env.get_template('auth.html')
    return html.render(error=error_msg)
def notfound_jinja():
    env = Environment(loader=FileSystemLoader('Templates'))
    html = env.get_template('404.html')
    return html.render()
def get_data(client_socket, client_address):
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
    method, path, version = (headers_lines[0]).split(b" ")
    headers_list = headers_lines[1:]
    headers = {}
    for header in headers_list:
        if b":" in header:
            key, value = header.split(b":",1)
            headers[key.decode().strip().lower()] = (value.decode()).strip()
    content_length = int(headers.get("content-length", 0))
    if(content_length > 1048576):
        response = (
            "HTTP/1.1 413 Payload Too Large\r\n"
            "Content-Length: 0\r\n"
            "\r\n"
        )
        logging.critical(f"We get so much content from {client_address[0]}")
        client_socket.sendall(response.encode())
        client_socket.close()
        return
    while len(body) < content_length:
        temp = client_socket.recv(4096)
        if temp:
            body += temp
        else: 
            break
    return method.decode(), path.decode(), version.decode(), headers, body.decode()
def connect(client_socket, client_address):
    try:
        logging.info(f"Client connected {client_address[0]}:{client_address[1]}")
        data = get_data(client_socket, client_address)
        if data is None:
            logging.error("Data is empty")
            return
        method, path, version, headers, body = data
        logging.info(f"We get method: {method}, path = {path} from user {client_address[0]}")
        if method == "GET" and path == "/login":
            body = auth_jinja().encode("utf-8")
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html\r\n"
                f"Content-Length: {len(body)}\r\n"
                "\r\n"
            ).encode("utf-8")
            response = response + body

        else:
            body = notfound_jinja().encode("utf-8")
            response = (
                "HTTP/1.1 404 Not Found\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Content-Type: text/html; charset=utf-8\r\n"
                "\r\n"
            ).encode("utf-8")
            response = response + body
            logging.error("We get 404 Not Found error")
        client_socket.sendall(response)
    except Exception as e:
        logging.exception(f"We get expect error {e} from {client_address[0]}")
    finally:
        client_socket.close()

try:
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(("127.0.0.1", 8080))
    server_socket.listen(5)
    logging.info("Server is start work on IP: 127.0.0.1 and port: 8080")
    while True:
        client_socket, client_address = server_socket.accept()
        thread = threading.Thread(target=connect, args=(client_socket, client_address))
        thread.start()
except Exception as e:
    logging.exception("We get fatal error, connection with server socket is close")
finally:
    server_socket.close()
