import socket
import threading
from flask import Flask, request, render_template
def get_data(client_socket):
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
    while len(body) < content_length:
        temp = client_socket.recv(4096)
        if temp:
            body += temp
        else: 
            break
    return method.decode(), path.decode(), version.decode(), headers, body.decode()
def connect(client_socket, client_address):
    print(f"Client with {client_address[0]} is connected!")

try:
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(("127.0.0.1", 8080))
    server_socket.listen(5)
    print("Server is listening on 127.0.0.1/8080")
    while True:
        client_socket, client_address = server_socket.accept()
        thread = threading.Thread(target=connect, args=(client_socket, client_address))
        thread.start()
except Exception as e:
    print(e)
finally:
    server_socket.close()
