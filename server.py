import sys
import socket
import thread
import pocketmsg as pm
import os

BUFFER_SIZE =  200

def service_message(msg, client, db_conn):
    
    msg_code, client_id, file_name, data = msg.split('|#|')
    print msg_code, client_id, file_name, data
    if msg_code == pm.msgCode.CREQ:
        # request to connection and sync
        if os.path.exists(file_name) is True:
            pass
        else :
            # send a request to send the total file
            ret_msg = pm.get_reqtot_msg(client_id,file_name,db_conn)
            client.sendall(ret_msg)  


def handle_request(client, addr, db_conn):
    while True:
        msg = client.recv(BUFFER_SIZE)
        if msg == "":
            continue
        service_message(msg, client, db_conn)
        
    client.close()

def _main():
    # create a server socket
    server = socket.socket()
    addr = ('', 0)
    server.bind(addr)
    print "Pocket Server Started at : {}".format(server.getsockname())
    server.listen(5)

    os.chdir(sys.argv[1])
    db_conn = pm.open_db()
    pm.create_table(db_conn)

    while True:
        client, addr = server.accept()
        thread.start_new_thread(handle_request,(client,addr,db_conn))
        
    server.close()


if __name__ == "__main__":
    _main()